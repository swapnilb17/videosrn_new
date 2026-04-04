"""Attach a JPEG poster image to MP4 as embedded thumbnail (attached_pic)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.services.ffmpeg_resolve import resolve_ffmpeg

logger = logging.getLogger(__name__)


def attach_thumbnail_to_mp4(
    mp4_path: Path,
    thumb_jpeg: Path,
    *,
    ffmpeg_explicit: str = "",
) -> None:
    if not mp4_path.is_file() or not thumb_jpeg.is_file():
        return
    ffmpeg = resolve_ffmpeg(explicit=ffmpeg_explicit or None)
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    tmp = mp4_path.with_name(mp4_path.stem + "._thumb.mp4")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(mp4_path),
        "-i",
        str(thumb_jpeg),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map",
        "1:v:0",
        "-c:v:0",
        "copy",
        "-c:a",
        "copy",
        "-c:v:1",
        "mjpeg",
        "-disposition:v:1",
        "attached_pic",
        str(tmp),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        logger.error("ffmpeg thumbnail attach failed: %s", proc.stderr)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError("Failed to attach thumbnail to MP4") from None
    tmp.replace(mp4_path)
