import logging
import subprocess
from pathlib import Path

from app.services.ffmpeg_resolve import resolve_ffmpeg, resolve_ffprobe
from app.services.video_watermark import (
    FrameOverlayAssets,
    ffmpeg_filter_scale_pad_then_overlay_wm,
    write_watermark_overlay_png,
)

logger = logging.getLogger(__name__)

_FFPROBE_TIMEOUT_SEC = 45
# Re-encode can be slow on small VMs; cap subprocess so the API job cannot hang forever.
_FFMPEG_OVERLAY_TIMEOUT_MIN_SEC = 300
_FFMPEG_OVERLAY_TIMEOUT_MAX_SEC = 1200


def _ffmpeg_overlay_timeout_sec(video_path: Path) -> int:
    try:
        n = video_path.stat().st_size
    except OSError:
        n = 0
    # Veo MP4s are short but large; small EC2 instances need headroom for libx264.
    scaled = 180 + min(900, max(0, n) // 120_000)
    return max(_FFMPEG_OVERLAY_TIMEOUT_MIN_SEC, min(_FFMPEG_OVERLAY_TIMEOUT_MAX_SEC, scaled))


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


def overlay_frame_watermark_on_mp4(
    video_path: Path,
    *,
    ffmpeg_explicit: str = "",
    assets: FrameOverlayAssets | None = None,
) -> None:
    """Burn slideshow-style credit overlay (see video_watermark) into an existing MP4."""
    ffmpeg = resolve_ffmpeg(explicit=ffmpeg_explicit or None)
    ffprobe = resolve_ffprobe(ffmpeg_explicit=ffmpeg_explicit or "")
    if not ffmpeg or not ffprobe:
        raise RuntimeError(
            "ffmpeg or ffprobe not available; cannot apply video credit overlay"
        )

    proc_dim = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=_FFPROBE_TIMEOUT_SEC,
    )
    if proc_dim.returncode != 0 or not (proc_dim.stdout or "").strip():
        raise RuntimeError(f"ffprobe dimension failed: {proc_dim.stderr}")
    parts = (proc_dim.stdout or "").strip().split("x")
    if len(parts) != 2:
        raise RuntimeError(f"unexpected ffprobe dimensions: {proc_dim.stdout!r}")
    w, h = int(parts[0]), int(parts[1])

    wm = video_path.parent / f".wm_credit_{video_path.stem}.png"
    tmp_out = video_path.parent / f".credit_out_{video_path.name}"
    try:
        write_watermark_overlay_png(w, h, wm, assets=assets or FrameOverlayAssets())
        has_audio = _ffprobe_has_audio_stream(ffprobe, video_path)
        fc = "[0:v][1:v]overlay=0:0:format=auto[outv]"
        enc_timeout = _ffmpeg_overlay_timeout_sec(video_path)
        # veryfast: much quicker than "fast" on small instances; fine for a short credit overlay pass.
        if has_audio:
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video_path),
                "-loop",
                "1",
                "-i",
                str(wm),
                "-filter_complex",
                fc,
                "-map",
                "[outv]",
                "-map",
                "0:a:0",
                "-c:v",
                "libx264",
                "-crf",
                "23",
                "-preset",
                "veryfast",
                "-threads",
                "0",
                "-c:a",
                "copy",
                str(tmp_out),
            ]
        else:
            cmd = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(video_path),
                "-loop",
                "1",
                "-i",
                str(wm),
                "-filter_complex",
                fc,
                "-map",
                "[outv]",
                "-c:v",
                "libx264",
                "-crf",
                "23",
                "-preset",
                "veryfast",
                "-threads",
                "0",
                str(tmp_out),
            ]
        logger.info(
            "ffmpeg credit overlay: timeout=%ss size=%s bytes",
            enc_timeout,
            video_path.stat().st_size if video_path.is_file() else 0,
        )
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=enc_timeout,
            )
        except subprocess.TimeoutExpired:
            logger.error(
                "ffmpeg credit overlay timed out after %ss (input %s bytes)",
                enc_timeout,
                video_path.stat().st_size if video_path.is_file() else 0,
            )
            raise RuntimeError(
                f"Video credit overlay timed out after {enc_timeout}s; try a larger instance or raise timeout"
            ) from None
        if proc.returncode != 0:
            logger.error("ffmpeg credit overlay failed: %s", proc.stderr)
            raise RuntimeError("Video credit overlay failed (ffmpeg)")
        tmp_out.replace(video_path)
    finally:
        wm.unlink(missing_ok=True)
        if tmp_out.is_file():
            tmp_out.unlink(missing_ok=True)

_FFMPEG_HINT = (
    "ffmpeg is not installed or not on your PATH. "
    "macOS: brew install ffmpeg  ·  Windows: https://ffmpeg.org/download.html"
)


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
    write_watermark_overlay_png(
        video_width,
        video_height,
        wm,
        assets=overlay_assets or FrameOverlayAssets(),
    )
    fc = ffmpeg_filter_scale_pad_then_overlay_wm(video_width, video_height)
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(image),
        "-loop",
        "1",
        "-i",
        str(wm),
        "-i",
        str(audio),
        "-filter_complex",
        fc,
        "-map",
        "[outv]",
        "-map",
        "2:a:0",
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
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
    if proc.returncode != 0:
        logger.error("ffmpeg mux failed: %s", proc.stderr)
        raise RuntimeError("Video mux failed (is ffmpeg installed and on PATH?)")
