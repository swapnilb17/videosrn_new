"""Slide images via Gemini native image generation (Nano Banana 2: gemini-3.1-flash-image-preview). Uses GEMINI_API_KEY + Generative Language generateContent."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.schemas import LanguageCode, ScriptPayload
from app.services.google_imagen import GEMINI_API_ROOT
from app.services.slide_image_plan import build_slide_image_jobs

logger = logging.getLogger(__name__)


class GeminiNativeImageError(Exception):
    pass


def _http_error_message(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error", {})
        return str(err.get("message", resp.text[:300]))
    except Exception:
        return resp.text[:300]


def _inline_blob(part: dict[str, Any]) -> tuple[str, str] | None:
    """Return (mime_type, base64_data) from a content part, or None."""
    blob = part.get("inlineData") or part.get("inline_data")
    if not isinstance(blob, dict):
        return None
    data = blob.get("data")
    if not isinstance(data, str) or len(data) < 80:
        return None
    mime = (
        blob.get("mimeType")
        or blob.get("mime_type")
        or "image/png"
    )
    if not isinstance(mime, str):
        mime = "image/png"
    return mime, data


def _extract_last_image_bytes(data: dict[str, Any]) -> bytes | None:
    """Use the last image part (final render after optional thought previews)."""
    cands = data.get("candidates")
    if not isinstance(cands, list) or not cands:
        return None
    first = cands[0]
    if not isinstance(first, dict):
        return None
    content = first.get("content")
    if not isinstance(content, dict):
        return None
    parts = content.get("parts")
    if not isinstance(parts, list):
        return None
    last_raw: tuple[str, str] | None = None
    for p in parts:
        if not isinstance(p, dict):
            continue
        got = _inline_blob(p)
        if got:
            last_raw = got
    if not last_raw:
        return None
    _mime, b64 = last_raw
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:
        return None
    if len(raw) < 100:
        return None
    return raw


def parse_generate_content_response_image(data: dict[str, Any]) -> bytes | None:
    """Decode image bytes from generateContent JSON (Generative Language or Vertex publishers model)."""
    return _extract_last_image_bytes(data)


async def _generate_one(
    client: httpx.AsyncClient,
    settings: Settings,
    prompt: str,
    out_path: Path,
    *,
    reference_png_bytes: bytes | None = None,
) -> None:
    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise GeminiNativeImageError("GEMINI_API_KEY is not set")

    model = (settings.gemini_native_image_model or "").strip()
    if not model:
        raise GeminiNativeImageError("GEMINI_NATIVE_IMAGE_MODEL is empty")

    url = f"{GEMINI_API_ROOT}/models/{model}:generateContent"
    params = {"key": key}
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
    body: dict[str, Any] = {
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

    max_attempts = 3
    last_error: GeminiNativeImageError | None = None

    for attempt in range(max_attempts):
        if attempt > 0:
            delay = 2 ** (attempt - 1)
            logger.info(
                "Gemini native image retry %s/%s after %ss",
                attempt + 1,
                max_attempts,
                delay,
            )
            await asyncio.sleep(delay)

        try:
            resp = await client.post(url, params=params, json=body)
        except httpx.RequestError as e:
            last_error = GeminiNativeImageError(
                f"Cannot reach Google Generative Language API: {e}. "
                "Check network and GEMINI_API_KEY."
            )
            if attempt < max_attempts - 1:
                continue
            raise last_error from e

        if resp.status_code in (429, 500, 503) and attempt < max_attempts - 1:
            logger.warning(
                "Gemini native image HTTP %s (transient), will retry: %s",
                resp.status_code,
                resp.text[:200],
            )
            last_error = GeminiNativeImageError(
                f"Gemini native image error {resp.status_code}: {_http_error_message(resp)}"
            )
            continue

        if resp.status_code >= 400:
            logger.warning("Gemini native image HTTP %s: %s", resp.status_code, resp.text[:800])
            raise GeminiNativeImageError(
                f"Gemini native image error {resp.status_code}: {_http_error_message(resp)}"
            )

        try:
            payload = resp.json()
        except Exception as e:
            raise GeminiNativeImageError("Invalid JSON from Gemini API") from e

        err = payload.get("error")
        if isinstance(err, dict) and err.get("message"):
            raise GeminiNativeImageError(str(err["message"]))

        raw = _extract_last_image_bytes(payload)
        if not raw:
            logger.warning(
                "Gemini native image: no image bytes in response keys=%s",
                list(payload.keys())[:12],
            )
            last_error = GeminiNativeImageError(
                "Gemini native image response contained no image bytes "
                "(safety filter, empty candidates, or model output text only)."
            )
            if attempt < max_attempts - 1:
                continue
            raise last_error

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw)
        return

    if last_error:
        raise last_error
    raise GeminiNativeImageError("Gemini native image failed after retries")


async def generate_gemini_native_slide_images(
    settings: Settings,
    topic: str,
    script: ScriptPayload,
    language: LanguageCode,
    slides_dir: Path,
    *,
    reserve_product_hero_zone: bool = False,
    product_reference_path: Path | None = None,
) -> list[Path]:
    if not (settings.gemini_api_key or "").strip():
        raise GeminiNativeImageError("GEMINI_API_KEY is not set")

    slides_dir.mkdir(parents=True, exist_ok=True)
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
                await _generate_one(
                    client,
                    settings,
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
        raise GeminiNativeImageError(f"Missing or empty slides: {[m.name for m in missing]}")

    return paths
