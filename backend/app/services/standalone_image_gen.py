"""Standalone image generation with failover.

Portrait mode (reference image provided):
  Tier 0:  OpenAI images.edit (dall-e-2 only; enforced in Settings)
  Tier 1+: Gemini / Vertex fallback

Text-to-image mode (no reference image):
  Tier 1:  Gemini 3.1 Flash Preview (native generateContent)
  Tier 2:  Vertex Gemini 2.5 Flash (Vertex generateContent)
  Tier 3:  Vertex Imagen (:predict)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.services.gemini_native_image import (
    GeminiNativeImageError,
    _generate_one as gemini_native_generate_one,
)
from app.services.vertex_gemini_image import (
    VertexGeminiImageError,
    _generate_one_location as vertex_gemini_generate_one_location,
)
from app.services.vertex_imagen import (
    GoogleImagenError,
    _credentials_path,
    _generate_one_with_region_failover as vertex_imagen_generate_one,
)
from app.services.openai_portrait import OpenAIPortraitError, generate_openai_portrait
from app.services.image_watermark import watermark_file

logger = logging.getLogger(__name__)

ASPECT_TO_IMAGEN = {
    "1:1": "1:1",
    "16:9": "16:9",
    "9:16": "9:16",
    "4:3": "4:3",
}


class ImageGenResult:
    __slots__ = ("path", "width", "height", "model")

    def __init__(self, path: Path, width: int, height: int, model: str):
        self.path = path
        self.width = width
        self.height = height
        self.model = model


async def generate_standalone_image(
    settings: Settings,
    prompt: str,
    *,
    aspect_ratio: str = "1:1",
    output_dir: Path | None = None,
    reference_image: bytes | None = None,
) -> ImageGenResult:
    """Generate a single image using the 3-tier failover chain.

    When *reference_image* is provided the user's photo is sent alongside the
    prompt so the model can produce a face-preserving stylised portrait.

    Returns ImageGenResult with the local file path and metadata.
    Raises if all tiers fail.
    """
    job_id = uuid.uuid4().hex[:12]
    if output_dir is None:
        output_dir = settings.artifact_root / f"img_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"image_{job_id}.png"

    patched = settings.model_copy(update={
        "imagen_aspect_ratio": ASPECT_TO_IMAGEN.get(aspect_ratio, aspect_ratio),
    })

    base = 1024
    w, h = base, base
    if aspect_ratio == "16:9":
        w, h = 1024, 576
    elif aspect_ratio == "9:16":
        w, h = 576, 1024
    elif aspect_ratio == "4:3":
        w, h = 1024, 768

    timeout = max(30.0, settings.gemini_timeout)

    # Tier 0: OpenAI images.edit (portrait mode only)
    openai_key = (settings.openai_api_key or "").strip()
    openai_edit_model = (settings.openai_image_edit_model or "dall-e-2").strip() or "dall-e-2"
    if reference_image and openai_key:
        try:
            await generate_openai_portrait(
                openai_key, reference_image, prompt, out_path,
                model=openai_edit_model,
                aspect_ratio=aspect_ratio,
                timeout=max(60.0, settings.openai_timeout),
            )
            if out_path.is_file() and out_path.stat().st_size > 100:
                watermark_file(out_path)
                logger.info("Standalone image: OpenAI portrait OK")
                return ImageGenResult(out_path, w, h, openai_edit_model)
        except (OpenAIPortraitError, Exception) as e:
            logger.warning("Standalone image: OpenAI portrait failed: %s", e)

    # Tier 1: Gemini 3.1 Flash Preview (native)
    if patched.gemini_native_image_configured():
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                await gemini_native_generate_one(
                    client, patched, prompt, out_path,
                    reference_png_bytes=reference_image,
                )
            if out_path.is_file() and out_path.stat().st_size > 100:
                watermark_file(out_path)
                logger.info("Standalone image: Gemini native OK")
                return ImageGenResult(out_path, w, h, "gemini-3.1-flash-preview")
        except (GeminiNativeImageError, Exception) as e:
            logger.warning("Standalone image: Gemini native failed: %s", e)

    # Tier 2: Vertex Gemini 2.5 Flash
    if patched.vertex_gemini_image_configured():
        cred_path = _credentials_path(patched)
        project = (patched.vertex_imagen_project_id or "").strip()
        model = (patched.vertex_gemini_image_model or "").strip()
        locations = patched.vertex_gemini_image_locations()
        if cred_path and project and model and locations:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    for loc in locations:
                        ok = await vertex_gemini_generate_one_location(
                            client, patched, cred_path, project, loc, model,
                            prompt, out_path,
                            reference_png_bytes=reference_image,
                        )
                        if ok and out_path.is_file() and out_path.stat().st_size > 100:
                            watermark_file(out_path)
                            logger.info("Standalone image: Vertex Gemini OK (location=%s)", loc)
                            return ImageGenResult(out_path, w, h, "gemini-2.5-flash")
            except (VertexGeminiImageError, Exception) as e:
                logger.warning("Standalone image: Vertex Gemini failed: %s", e)

    # Tier 3: Vertex Imagen
    if patched.vertex_imagen_configured():
        cred_path = _credentials_path(patched)
        project = (patched.vertex_imagen_project_id or "").strip()
        regions_raw = (patched.vertex_imagen_regions or "").strip()
        regions = [r.strip() for r in regions_raw.split(",") if r.strip()]
        eff_model = patched.imagen_model_effective()
        if cred_path and project and regions:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    await vertex_imagen_generate_one(
                        client, patched, cred_path, project, regions, eff_model,
                        prompt, out_path,
                    )
                if out_path.is_file() and out_path.stat().st_size > 100:
                    watermark_file(out_path)
                    logger.info("Standalone image: Vertex Imagen OK")
                    return ImageGenResult(out_path, w, h, "imagen-4.0")
            except (GoogleImagenError, Exception) as e:
                logger.warning("Standalone image: Vertex Imagen failed: %s", e)

    raise RuntimeError(
        "All image generation tiers failed. Check API keys, service account, and quotas."
    )
