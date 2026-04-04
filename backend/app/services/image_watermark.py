"""Watermark utility for generated still images.

Composites a subtle 'EnablyAI.com' text badge on the bottom-left of any
PIL Image or raw PNG bytes on disk.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

WATERMARK_TEXT = "EnablyAI.com"

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for raw in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(raw, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def apply_watermark(img: Image.Image) -> Image.Image:
    """Return a copy of *img* with the EnablyAI.com watermark on the bottom-left."""
    canvas = img.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    ref = min(canvas.width, canvas.height)
    font_size = max(14, ref // 38)
    font = _load_font(font_size)

    margin_x = max(12, ref // 50)
    margin_y = max(12, ref // 50)
    pad_x = max(6, font_size // 3)
    pad_y = max(4, font_size // 4)

    bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    x_text = margin_x + pad_x
    y_text = canvas.height - margin_y - pad_y - th

    pill_x0 = margin_x
    pill_y0 = y_text - pad_y
    pill_x1 = x_text + tw + pad_x
    pill_y1 = y_text + th + pad_y
    radius = max(6, font_size // 3)

    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x1, pill_y1],
        radius=radius,
        fill=(0, 0, 0, 140),
    )
    draw.text((x_text, y_text), WATERMARK_TEXT, fill=(255, 255, 255, 220), font=font)

    result = Image.alpha_composite(canvas, overlay)
    return result.convert("RGB")


def watermark_file(path: Path) -> None:
    """Read a PNG/JPEG from *path*, apply the watermark, and overwrite it."""
    try:
        img = Image.open(path)
        result = apply_watermark(img)
        result.save(path, format="PNG")
        logger.debug("Watermark applied to %s", path.name)
    except Exception:
        logger.warning("Failed to apply watermark to %s", path.name, exc_info=True)
