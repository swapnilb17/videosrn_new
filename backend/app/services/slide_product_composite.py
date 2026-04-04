"""Composite the user-uploaded product image into each generated slide (hero placement)."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageFilter

from app.services.video_watermark import _paste_logo_blended

logger = logging.getLogger(__name__)


def composite_user_product_onto_slide(slide_path: Path, product_png_path: Path) -> None:
    """
    Draw the user's product (RGBA PNG) onto the slide at lower-left, large enough to read as the hero product.
    First blurs the lower-left band under the paste so busy model output does not clash with the cut-out photo.
    Overwrites slide_path in place. No-op if files are missing or unreadable.
    """
    if not slide_path.is_file() or not product_png_path.is_file():
        return
    try:
        slide = Image.open(slide_path).convert("RGBA")
    except OSError as e:
        logger.info("Could not open slide for product composite %s: %s", slide_path, e)
        return
    try:
        pim = Image.open(product_png_path).convert("RGBA")
    except OSError as e:
        logger.info("Could not open product image for composite: %s", e)
        return

    w, h = slide.size
    if w < 32 or h < 32:
        return
    ref = min(w, h)
    margin_x = max(12, ref // 40)
    margin_y = max(12, ref // 40)
    # Large enough to act as the on-screen product (not a tiny corner badge)
    max_side = max(56, int(ref * 0.44))
    pim.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    pw, ph = pim.size
    if pw < 2 or ph < 2:
        return
    lx = margin_x
    ty = h - margin_y - ph
    # Enforce the prompt "reserved zone" in pixels: models often ignore empty-corner instructions.
    pad = max(10, ref // 28)
    cx0 = max(0, lx - pad)
    cy0 = max(0, ty - pad)
    cx1 = min(w, lx + pw + pad)
    cy1 = h
    if cx1 > cx0 + 4 and cy1 > cy0 + 4:
        patch = slide.crop((cx0, cy0, cx1, cy1))
        blur_r = max(14, min(36, max(pw, ph) // 5))
        softened = patch.filter(ImageFilter.GaussianBlur(blur_r))
        slide.paste(softened, (cx0, cy0))
    _paste_logo_blended(slide, pim, lx, ty)

    try:
        slide.convert("RGB").save(slide_path, format="PNG", optimize=True)
    except OSError as e:
        logger.warning("Could not save slide after product composite %s: %s", slide_path, e)
