"""Validate and persist user-uploaded branding logos for video overlay."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.services.user_assets import save_optional_rgba_png


async def save_branding_logo_from_upload(logo: UploadFile | None, dest_png: Path) -> bool:
    """Save an optional logo to dest_png (RGBA PNG). Returns False if no file was provided."""
    return await save_optional_rgba_png(logo, dest_png, label="Logo")
