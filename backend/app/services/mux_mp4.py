import logging
import subprocess
from pathlib import Path

from app.services.ffmpeg_resolve import resolve_ffmpeg
from app.services.video_watermark import (
    FrameOverlayAssets,
    ffmpeg_filter_scale_pad_then_overlay_wm,
    write_watermark_overlay_png,
)

logger = logging.getLogger(__name__)

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
