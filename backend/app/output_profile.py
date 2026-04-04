"""Content format (aspect) × output quality → video pixels and image API settings."""

from __future__ import annotations

from typing import Literal

from app.config import Settings

ContentFormat = Literal["youtube_landscape", "reels_shorts", "instagram_fb"]
OutputQuality = Literal["720p", "1080p", "4k", "8k"]

# (format, quality) → (video_width, video_height)
_DIMENSIONS: dict[tuple[ContentFormat, OutputQuality], tuple[int, int]] = {
    ("youtube_landscape", "720p"): (1280, 720),
    ("youtube_landscape", "1080p"): (1920, 1080),
    ("youtube_landscape", "4k"): (3840, 2160),
    ("youtube_landscape", "8k"): (7680, 4320),
    ("reels_shorts", "720p"): (720, 1280),
    ("reels_shorts", "1080p"): (1080, 1920),
    ("reels_shorts", "4k"): (2160, 3840),
    ("reels_shorts", "8k"): (4320, 7680),
    ("instagram_fb", "720p"): (720, 720),
    ("instagram_fb", "1080p"): (1080, 1080),
    ("instagram_fb", "4k"): (2160, 2160),
    ("instagram_fb", "8k"): (4320, 4320),
}

_ASPECT_FOR_FORMAT: dict[ContentFormat, str] = {
    "youtube_landscape": "16:9",
    "reels_shorts": "9:16",
    "instagram_fb": "1:1",
}

# Gemini / Imagen imageConfig.imageSize and Imagen sampleImageSize (provider may cap; mux still uses full canvas).
_IMAGEN_SIZE: dict[OutputQuality, str] = {
    "720p": "1K",
    "1080p": "2K",
    "4k": "4K",
    "8k": "4K",
}


def parse_content_format_form(raw: str | None) -> ContentFormat | None:
    """None = omit field (legacy: do not override format from env)."""
    s = (raw or "").strip().lower()
    if not s:
        return None
    if s in _ASPECT_FOR_FORMAT:
        return s  # type: ignore[return-value]
    raise ValueError(
        "content_format must be one of: youtube_landscape, reels_shorts, instagram_fb"
    )


def parse_output_quality_form(raw: str | None) -> OutputQuality | None:
    """None = omit field (legacy: do not override quality from env)."""
    s = (raw or "").strip().lower()
    if not s:
        return None
    if s == "4k":
        return "4k"
    if s == "8k":
        return "8k"
    if s in ("720p", "1080p"):
        return s  # type: ignore[return-value]
    raise ValueError("output_quality must be one of: 720p, 1080p, 4k, 8k")


def build_visual_settings_from_forms(
    base: Settings,
    raw_format: str | None,
    raw_quality: str | None,
) -> tuple[Settings, ContentFormat | None, OutputQuality | None]:
    """
    If both form fields are empty, returns (base, None, None) for backward compatibility.
    If only one is set, defaults the other to reels_shorts / 1080p respectively.
    """
    fmt = parse_content_format_form(raw_format)
    qual = parse_output_quality_form(raw_quality)
    if fmt is None and qual is None:
        return base, None, None
    fmt_f: ContentFormat = fmt or "reels_shorts"
    qual_f: OutputQuality = qual or "1080p"
    w, h = _DIMENSIONS[(fmt_f, qual_f)]
    ar = _ASPECT_FOR_FORMAT[fmt_f]
    imagen_sz = _IMAGEN_SIZE[qual_f]
    out = base.model_copy(
        update={
            "video_width": w,
            "video_height": h,
            "imagen_aspect_ratio": ar,
            "imagen_image_size": imagen_sz,
        }
    )
    return out, fmt_f, qual_f
