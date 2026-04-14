import logging
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from app.services.ffmpeg_resolve import resolve_ffmpeg, resolve_ffprobe
from app.services.video_watermark import (
    FrameOverlayAssets,
    write_watermark_overlay_png,
)

logger = logging.getLogger(__name__)

_FRAME_EXTRACT_TIMEOUT = 120
_FRAME_REENCODE_TIMEOUT = 600

# Avoid subprocess pipe deadlock with capture_output=True (see slideshow_video._FF_QUIET).
_FF_QUIET = ("-hide_banner", "-nostats", "-loglevel", "error")

_FFPROBE_TIMEOUT_SEC = 45
# PIL frame-by-frame overlay: extract + composite + re-encode is bounded by these two.
# asyncio.wait_for around asyncio.to_thread(overlay_...) must exceed the sum.
FFMPEG_OVERLAY_ASYNC_GUARD_SEC = float(_FRAME_EXTRACT_TIMEOUT + _FRAME_REENCODE_TIMEOUT + 120)


def _ffprobe_has_audio_stream(ffprobe: str, video_path: Path) -> bool:
    r = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=_FFPROBE_TIMEOUT_SEC,
    )
    return r.returncode == 0 and bool((r.stdout or "").strip())


def _ffprobe_fps(ffprobe: str, video_path: Path) -> str:
    """Return the r_frame_rate string (e.g. '24/1') for re-encode."""
    r = subprocess.run(
        [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True, check=False, timeout=_FFPROBE_TIMEOUT_SEC,
    )
    return (r.stdout or "24").strip() or "24"


def overlay_frame_watermark_on_mp4(
    video_path: Path,
    *,
    ffmpeg_explicit: str = "",
    assets: FrameOverlayAssets | None = None,
) -> None:
    """Burn credit overlay into an existing MP4.

    Uses PIL to composite the watermark frame-by-frame, avoiding FFmpeg's
    overlay filter which is catastrophically slow on ARM/Graviton.
    """
    ffmpeg = resolve_ffmpeg(explicit=ffmpeg_explicit or None)
    ffprobe = resolve_ffprobe(ffmpeg_explicit=ffmpeg_explicit or "")
    if not ffmpeg or not ffprobe:
        raise RuntimeError(
            "ffmpeg or ffprobe not available; cannot apply video credit overlay"
        )

    proc_dim = subprocess.run(
        [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(video_path),
        ],
        capture_output=True, text=True, check=False, timeout=_FFPROBE_TIMEOUT_SEC,
    )
    if proc_dim.returncode != 0 or not (proc_dim.stdout or "").strip():
        raise RuntimeError(f"ffprobe dimension failed: {proc_dim.stderr}")
    parts = (proc_dim.stdout or "").strip().split("x")
    if len(parts) != 2:
        raise RuntimeError(f"unexpected ffprobe dimensions: {proc_dim.stdout!r}")
    w, h = int(parts[0]), int(parts[1])

    wm = video_path.parent / f".wm_credit_{video_path.stem}.png"
    frames_dir = video_path.parent / f".frames_{video_path.stem}"
    tmp_out = video_path.parent / f".credit_out_{video_path.name}"
    try:
        write_watermark_overlay_png(w, h, wm, assets=assets or FrameOverlayAssets())
        has_audio = _ffprobe_has_audio_stream(ffprobe, video_path)
        fps = _ffprobe_fps(ffprobe, video_path)

        # 1. Extract frames as JPEG (fast, small on disk)
        frames_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "credit overlay: extracting frames via PIL path (size=%s bytes)",
            video_path.stat().st_size if video_path.is_file() else 0,
        )
        r = subprocess.run(
            [
                ffmpeg, "-y", *_FF_QUIET,
                "-i", str(video_path),
                "-qscale:v", "1",
                str(frames_dir / "f_%06d.jpg"),
            ],
            capture_output=True, text=True, check=False, timeout=_FRAME_EXTRACT_TIMEOUT,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Frame extraction failed: {r.stderr[:500]}")

        # 2. Composite watermark on each frame in PIL (fast on all archs)
        wm_img = Image.open(wm).convert("RGBA")
        frame_files = sorted(frames_dir.glob("f_*.jpg"))
        for fp in frame_files:
            bg = Image.open(fp).convert("RGBA")
            bg = Image.alpha_composite(bg, wm_img)
            bg.convert("RGB").save(fp, format="JPEG", quality=97)
        logger.info("credit overlay: composited %d frames", len(frame_files))

        # 3. Re-encode composited frames + original audio
        cmd = [
            ffmpeg, "-y", *_FF_QUIET,
            "-framerate", fps,
            "-i", str(frames_dir / "f_%06d.jpg"),
        ]
        if has_audio:
            cmd += ["-i", str(video_path), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "copy"]
        cmd += [
            "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-threads", "0",
            str(tmp_out),
        ]
        r = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=_FRAME_REENCODE_TIMEOUT,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Frame re-encode failed: {r.stderr[:500]}")

        tmp_out.replace(video_path)
        logger.info("credit overlay: done (PIL frame path)")
    finally:
        wm.unlink(missing_ok=True)
        if frames_dir.is_dir():
            shutil.rmtree(frames_dir, ignore_errors=True)
        if tmp_out.is_file():
            tmp_out.unlink(missing_ok=True)

_FFMPEG_HINT = (
    "ffmpeg is not installed or not on your PATH. "
    "macOS: brew install ffmpeg  ·  Windows: https://ffmpeg.org/download.html"
)


def _pil_composite_still(
    slide: Path, wm: Path, out: Path, width: int, height: int,
) -> None:
    """Scale slide to fill target, center-crop, composite watermark, save as RGB PNG."""
    bg = Image.open(slide).convert("RGBA")
    scale = max(width / bg.width, height / bg.height)
    nw, nh = round(bg.width * scale), round(bg.height * scale)
    if (nw, nh) != bg.size:
        bg = bg.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - width) // 2
    top = (nh - height) // 2
    bg = bg.crop((left, top, left + width, top + height))
    wm_img = Image.open(wm).convert("RGBA")
    bg = Image.alpha_composite(bg, wm_img)
    bg.convert("RGB").save(out, format="PNG")


def mux_still_image_and_audio(
    image: Path,
    audio: Path,
    out_mp4: Path,
    *,
    ffmpeg_explicit: str = "",
    video_width: int = 1080,
    video_height: int = 1920,
    overlay_assets: FrameOverlayAssets | None = None,
) -> None:
    ffmpeg = resolve_ffmpeg(explicit=ffmpeg_explicit or None)
    if not ffmpeg:
        raise RuntimeError(_FFMPEG_HINT)

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    wm = out_mp4.parent / f".wm_{out_mp4.stem}.png"
    comp = out_mp4.parent / f".comp_{out_mp4.stem}.png"
    write_watermark_overlay_png(
        video_width,
        video_height,
        wm,
        assets=overlay_assets or FrameOverlayAssets(),
    )
    _pil_composite_still(image, wm, comp, video_width, video_height)
    cmd = [
        ffmpeg,
        "-y",
        *_FF_QUIET,
        "-loop",
        "1",
        "-i",
        str(comp),
        "-i",
        str(audio),
        "-vf",
        "format=yuv420p",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-pix_fmt",
        "yuv420p",
        str(out_mp4),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(_FFMPEG_HINT) from e
    finally:
        wm.unlink(missing_ok=True)
        comp.unlink(missing_ok=True)
    if proc.returncode != 0:
        logger.error("ffmpeg mux failed: %s", proc.stderr)
        raise RuntimeError("Video mux failed (is ffmpeg installed and on PATH?)")
