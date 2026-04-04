"""Imagen slide images: Vertex AI (primary when IMAGEN_USE_VERTEX=1) or Google AI Studio (GEMINI_API_KEY)."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.schemas import LanguageCode, ScriptPayload
from app.services.image_prompts import script_visual_segments
from app.services.slide_image_plan import build_slide_image_jobs

logger = logging.getLogger(__name__)

GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


class GoogleImagenError(Exception):
    pass


def build_imagen_predict_parameters(settings: Settings, *, vertex: bool = False) -> dict[str, Any]:
    """Shared Imagen :predict parameters. Imagen 4 on Vertex expects sampleImageSize (imageSize alone can return no bytes)."""
    size = (settings.imagen_image_size or "1K").strip()
    params: dict[str, Any] = {
        "sampleCount": 1,
        "aspectRatio": (settings.imagen_aspect_ratio or "9:16").strip(),
        "personGeneration": (settings.imagen_person_generation or "allow_adult").strip(),
        "sampleImageSize": size,
        "imageSize": size,
    }
    safety = (settings.imagen_safety_setting or "").strip()
    if safety:
        params["safetySetting"] = safety
    if vertex:
        params["language"] = "en"
        params["includeRaiReason"] = True
    return params


def _predictions_debug_summary(data: dict[str, Any]) -> str:
    preds = data.get("predictions")
    if preds is None:
        return f"no predictions key; top-level keys={list(data.keys())[:12]}"
    if not isinstance(preds, list):
        return f"predictions not a list: {type(preds).__name__}"
    if len(preds) == 0:
        return "predictions=[] (empty — often RAI filter or quota; try IMAGEN_SAFETY_SETTING=block_only_high)"
    bits: list[str] = []
    for i, p in enumerate(preds[:4]):
        if not isinstance(p, dict):
            bits.append(f"[{i}]={type(p).__name__}")
            continue
        has_b64 = bool(
            p.get("bytesBase64Encoded")
            or p.get("bytes_base64_encoded")
            or p.get("imageBytes")
        )
        rai = p.get("raiFilteredReason") or p.get("rai_filtered_reason")
        bits.append(
            f"[{i}] keys={sorted(p.keys())} has_image_bytes={has_b64} rai={repr(rai)[:120] if rai else 'none'}"
        )
    return "; ".join(bits)


def _image_bytes_from_prediction(pred: Any) -> bytes | None:
    if pred is None:
        return None
    if isinstance(pred, str) and len(pred) > 80:
        try:
            return base64.b64decode(pred, validate=False)
        except Exception:
            return None
    if not isinstance(pred, dict):
        return None
    for key in ("bytesBase64Encoded", "bytes_base64_encoded", "imageBytes", "image_bytes", "b64"):
        v = pred.get(key)
        if isinstance(v, str) and len(v) > 80:
            try:
                return base64.b64decode(v, validate=False)
            except Exception:
                continue
    for nest_key in ("image", "generatedImage", "generated_image", "output"):
        inner = pred.get(nest_key)
        if inner is not None:
            got = _image_bytes_from_prediction(inner)
            if got:
                return got
    return None


def _extract_first_image_bytes(data: dict[str, Any]) -> bytes | None:
    preds = data.get("predictions")
    if isinstance(preds, list):
        for p in preds:
            b = _image_bytes_from_prediction(p)
            if b and len(b) > 100:
                return b
    for key in ("generatedImages", "generated_images"):
        block = data.get(key)
        if isinstance(block, list):
            for item in block:
                b = _image_bytes_from_prediction(item)
                if b and len(b) > 100:
                    return b
    return None


def _http_error_message(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error", {})
        return str(err.get("message", resp.text[:300]))
    except Exception:
        return resp.text[:300]


async def _generate_one(
    client: httpx.AsyncClient,
    settings: Settings,
    prompt: str,
    out_path: Path,
) -> None:
    key = (settings.gemini_api_key or "").strip()
    if not key:
        raise GoogleImagenError("GEMINI_API_KEY is not set")

    model = settings.imagen_model_effective()
    if not model:
        raise GoogleImagenError("IMAGEN_MODEL is empty")

    url = f"{GEMINI_API_ROOT}/models/{model}:predict"
    params = {"key": key}
    body: dict[str, Any] = {
        "instances": [{"prompt": prompt}],
        "parameters": build_imagen_predict_parameters(settings, vertex=False),
    }

    max_attempts = 3
    last_error: GoogleImagenError | None = None

    for attempt in range(max_attempts):
        if attempt > 0:
            delay = 2 ** (attempt - 1)
            logger.info("Imagen retry %s/%s after %ss", attempt + 1, max_attempts, delay)
            await asyncio.sleep(delay)

        try:
            resp = await client.post(url, params=params, json=body)
        except httpx.RequestError as e:
            last_error = GoogleImagenError(
                f"Cannot reach Google Generative Language API: {e}. "
                "Check network and GEMINI_API_KEY (Google AI Studio)."
            )
            if attempt < max_attempts - 1:
                continue
            raise last_error from e

        if resp.status_code in (429, 500, 503) and attempt < max_attempts - 1:
            logger.warning(
                "Imagen HTTP %s (transient), will retry: %s",
                resp.status_code,
                resp.text[:200],
            )
            last_error = GoogleImagenError(
                f"Imagen API error {resp.status_code}: {_http_error_message(resp)}"
            )
            continue

        if resp.status_code >= 400:
            logger.warning("Imagen HTTP %s: %s", resp.status_code, resp.text[:800])
            raise GoogleImagenError(
                f"Imagen API error {resp.status_code}: {_http_error_message(resp)}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise GoogleImagenError("Invalid JSON from Imagen API") from e

        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            raise GoogleImagenError(str(err["message"]))

        raw = _extract_first_image_bytes(data)
        if not raw:
            logger.warning(
                "Imagen (AI Studio) no image bytes. %s",
                _predictions_debug_summary(data),
            )
            last_error = GoogleImagenError(
                "Imagen response contained no image bytes (content may have been filtered). "
                "Try imagen-4.0-fast-generate-001, IMAGEN_MAX_CONCURRENT=1, or a simpler English prompt."
            )
            if attempt < max_attempts - 1:
                continue
            raise last_error

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw)
        return

    if last_error:
        raise last_error
    raise GoogleImagenError("Imagen generation failed after retries")


async def generate_imagen_slide_images(
    settings: Settings,
    topic: str,
    script: ScriptPayload,
    language: LanguageCode,
    slides_dir: Path,
    *,
    reserve_product_hero_zone: bool = False,
) -> list[Path]:
    if settings.vertex_imagen_configured():
        from app.services.vertex_imagen import generate_vertex_imagen_slide_images

        return await generate_vertex_imagen_slide_images(
            settings,
            topic,
            script,
            language,
            slides_dir,
            reserve_product_hero_zone=reserve_product_hero_zone,
        )

    if not (settings.gemini_api_key or "").strip():
        raise GoogleImagenError("GEMINI_API_KEY is not set")

    slides_dir.mkdir(parents=True, exist_ok=True)
    jobs = build_slide_image_jobs(
        topic,
        script,
        language,
        slides_dir,
        reserve_product_hero_zone=reserve_product_hero_zone,
        product_reference_path=None,
    )

    sem = asyncio.Semaphore(max(1, settings.imagen_max_concurrent))
    timeout = max(30.0, settings.gemini_timeout)

    async with httpx.AsyncClient(timeout=timeout) as client:

        async def _run(p: str, out: Path) -> None:
            async with sem:
                await _generate_one(client, settings, p, out)

        await asyncio.gather(*[_run(j.prompt, j.output_path) for j in jobs])

    paths = [j.output_path for j in jobs]

    missing = [p for p in paths if not p.is_file() or p.stat().st_size < 100]
    if missing:
        raise GoogleImagenError(f"Missing or empty slides: {[m.name for m in missing]}")

    return paths
