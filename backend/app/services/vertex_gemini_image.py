"""Slide images via Vertex AI Gemini image models (e.g. gemini-2.5-flash-image) :generateContent. Same SA/project as Vertex Imagen."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.schemas import LanguageCode, ScriptPayload
from app.services.gemini_native_image import parse_generate_content_response_image
from app.services.google_imagen import _http_error_message
from app.services.slide_image_plan import build_slide_image_jobs
from app.services.vertex_imagen import (
    _access_token_sync,
    _credentials_path,
    response_indicates_try_next_region,
)

logger = logging.getLogger(__name__)


class VertexGeminiImageError(Exception):
    pass


def _generate_content_url(project: str, location: str, model: str) -> str:
    loc = (location or "").strip()
    model = (model or "").strip()
    path = (
        f"/v1/projects/{project}/locations/{loc}/publishers/google/models/{model}:generateContent"
    )
    if loc.lower() == "global":
        return f"https://aiplatform.googleapis.com{path}"
    return f"https://{loc}-aiplatform.googleapis.com{path}"


def _generation_body(
    settings: Settings,
    prompt: str,
    *,
    reference_png_bytes: bytes | None = None,
) -> dict[str, Any]:
    aspect = (settings.imagen_aspect_ratio or "9:16").strip()
    size = (settings.imagen_image_size or "1K").strip()
    parts: list[dict[str, Any]] = []
    if reference_png_bytes:
        parts.append(
            {
                "inlineData": {
                    "mimeType": "image/png",
                    "data": base64.b64encode(reference_png_bytes).decode("ascii"),
                }
            }
        )
    parts.append({"text": prompt})
    return {
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {
                "aspectRatio": aspect,
                "imageSize": size,
            },
        },
    }


async def _generate_one_location(
    client: httpx.AsyncClient,
    settings: Settings,
    credentials_path: str,
    project: str,
    location: str,
    model: str,
    prompt: str,
    out_path: Path,
    *,
    reference_png_bytes: bytes | None = None,
) -> bool:
    """Try this location with backoff on 429/503 and transient errors (same as native Gemini image)."""
    url = _generate_content_url(project, location, model)
    body = _generation_body(settings, prompt, reference_png_bytes=reference_png_bytes)
    max_attempts = 3
    last_note = ""

    for attempt in range(max_attempts):
        if attempt > 0:
            delay = 2 ** (attempt - 1)
            logger.info(
                "Vertex Gemini image location=%s backoff retry %s/%s after %ss",
                location,
                attempt + 1,
                max_attempts,
                delay,
            )
            await asyncio.sleep(delay)

        try:
            token = await asyncio.to_thread(_access_token_sync, credentials_path)
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=body,
            )
        except httpx.RequestError as e:
            last_note = str(e)
            logger.warning(
                "Vertex Gemini image location=%s request error (attempt %s/%s): %s",
                location,
                attempt + 1,
                max_attempts,
                e,
            )
            if attempt == max_attempts - 1:
                return False
            continue

        if response_indicates_try_next_region(resp):
            last_note = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning(
                "Vertex Gemini image location=%s HTTP %s (transient), will retry: %s",
                location,
                resp.status_code,
                resp.text[:300],
            )
            if attempt == max_attempts - 1:
                return False
            continue

        if resp.status_code >= 400:
            raise VertexGeminiImageError(
                f"Vertex Gemini image {location} error {resp.status_code}: {_http_error_message(resp)}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise VertexGeminiImageError(
                f"Vertex Gemini image {location}: invalid JSON"
            ) from e

        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            raise VertexGeminiImageError(f"Vertex Gemini image {location}: {err['message']}")

        raw = parse_generate_content_response_image(data)
        if not raw or len(raw) < 100:
            logger.warning(
                "Vertex Gemini image %s: no image in response keys=%s",
                location,
                list(data.keys())[:12],
            )
            return False

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw)
        logger.info("Vertex Gemini image ok location=%s out=%s", location, out_path.name)
        return True

    return False


async def _generate_one_with_location_failover(
    client: httpx.AsyncClient,
    settings: Settings,
    credentials_path: str,
    project: str,
    locations: list[str],
    model: str,
    prompt: str,
    out_path: Path,
    *,
    reference_png_bytes: bytes | None = None,
) -> None:
    model = (model or "").strip()
    if not model:
        raise VertexGeminiImageError("VERTEX_GEMINI_IMAGE_MODEL is empty")

    last_note = ""
    for location in locations:
        ok = await _generate_one_location(
            client,
            settings,
            credentials_path,
            project,
            location,
            model,
            prompt,
            out_path,
            reference_png_bytes=reference_png_bytes,
        )
        if ok:
            return
        last_note = f"location {location} quota/rate, network, or empty image after retries"

    raise VertexGeminiImageError(
        "Vertex Gemini image failed in all configured locations (quota, network, or empty image). "
        f"Last: {last_note}. Tried: {', '.join(locations)}"
    )


async def generate_vertex_gemini_slide_images(
    settings: Settings,
    topic: str,
    script: ScriptPayload,
    language: LanguageCode,
    slides_dir: Path,
    *,
    reserve_product_hero_zone: bool = False,
    product_reference_path: Path | None = None,
) -> list[Path]:
    if not settings.vertex_gemini_image_configured():
        raise VertexGeminiImageError(
            "Vertex Gemini image is not configured (VERTEX_GEMINI_IMAGE_FAILOVER, GCP credentials JSON, "
            "VERTEX_IMAGEN_PROJECT or GOOGLE_CLOUD_PROJECT, VERTEX_GEMINI_IMAGE_MODEL, "
            "and VERTEX_GEMINI_IMAGE_REGIONS or VERTEX_IMAGEN_REGIONS)"
        )

    credentials_path = _credentials_path(settings)
    if not credentials_path:
        raise VertexGeminiImageError(
            "No GCP service account JSON (GOOGLE_TTS_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS)"
        )

    project = (settings.vertex_imagen_project_id or "").strip()
    locations = settings.vertex_gemini_image_locations()
    model = (settings.vertex_gemini_image_model or "").strip()

    slides_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Vertex Gemini image model=%s locations=%s",
        model,
        ",".join(locations),
    )
    jobs = build_slide_image_jobs(
        topic,
        script,
        language,
        slides_dir,
        reserve_product_hero_zone=reserve_product_hero_zone,
        product_reference_path=product_reference_path,
    )

    sem = asyncio.Semaphore(max(1, settings.imagen_max_concurrent))
    timeout = max(30.0, settings.gemini_timeout)

    async with httpx.AsyncClient(timeout=timeout) as client:

        async def _run(prompt: str, out: Path, ref: bytes | None) -> None:
            async with sem:
                await _generate_one_with_location_failover(
                    client,
                    settings,
                    credentials_path,
                    project,
                    locations,
                    model,
                    prompt,
                    out,
                    reference_png_bytes=ref,
                )

        await asyncio.gather(
            *[_run(j.prompt, j.output_path, j.reference_png_bytes) for j in jobs]
        )

    paths = [j.output_path for j in jobs]
    missing = [p for p in paths if not p.is_file() or p.stat().st_size < 100]
    if missing:
        raise VertexGeminiImageError(
            f"Missing or empty slides: {[m.name for m in missing]}"
        )

    return paths
