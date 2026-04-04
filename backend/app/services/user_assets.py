"""Optional user uploads: images (logo, product, CTA, thumbnail) and address text."""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
MAX_IMAGE_SIDE_PX = 1024
MAX_THUMB_SIDE_PX = 1280
MAX_ADDRESS_CHARS = 400


def normalize_address_form(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) > MAX_ADDRESS_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Address must be {MAX_ADDRESS_CHARS} characters or fewer.",
        )
    return re.sub(r"\s+", " ", s)


async def save_optional_rgba_png(upload: UploadFile | None, dest: Path, *, label: str) -> bool:
    """
    Validate PNG/JPEG/WebP upload and save as RGBA PNG (downscaled if huge).
    label: human name for errors ("Logo", "Product image", …).
    """
    if upload is None:
        return False
    fn = (upload.filename or "").strip()
    if not fn:
        return False

    ct = (upload.content_type or "").split(";")[0].strip().lower()
    if ct not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be PNG, JPEG, or WebP.",
        )

    data = await upload.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be 2MB or smaller.",
        )
    if len(data) < 32:
        raise HTTPException(status_code=400, detail=f"{label} file is empty or too small.")

    try:
        im = Image.open(BytesIO(data))
        im.load()
    except Exception as e:
        logger.info("Invalid %s: %s", label, e)
        raise HTTPException(status_code=400, detail=f"Could not read {label.lower()}.") from e

    im = im.convert("RGBA")
    if max(im.size) > MAX_IMAGE_SIDE_PX:
        im.thumbnail((MAX_IMAGE_SIDE_PX, MAX_IMAGE_SIDE_PX), Image.Resampling.LANCZOS)

    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="PNG")
    return True


async def save_optional_thumbnail_jpeg(upload: UploadFile | None, dest_jpg: Path) -> bool:
    """Save optional cover thumbnail as JPEG for MP4 attached_pic."""
    if upload is None:
        return False
    fn = (upload.filename or "").strip()
    if not fn:
        return False

    ct = (upload.content_type or "").split(";")[0].strip().lower()
    if ct not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Thumbnail must be PNG, JPEG, or WebP.",
        )

    data = await upload.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Thumbnail must be 2MB or smaller.")
    if len(data) < 32:
        raise HTTPException(status_code=400, detail="Thumbnail file is empty or too small.")

    try:
        im = Image.open(BytesIO(data))
        im.load()
    except Exception as e:
        logger.info("Invalid thumbnail: %s", e)
        raise HTTPException(status_code=400, detail="Could not read thumbnail.") from e

    im = im.convert("RGB")
    if max(im.size) > MAX_THUMB_SIDE_PX:
        im.thumbnail((MAX_THUMB_SIDE_PX, MAX_THUMB_SIDE_PX), Image.Resampling.LANCZOS)

    dest_jpg.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest_jpg, format="JPEG", quality=90, optimize=True)
    return True
