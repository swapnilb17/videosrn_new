"""Vertex AI Imagen (regional :predict). Primary region default us-central1; list supports future multi-region failover."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.schemas import LanguageCode, ScriptPayload
from app.services.google_imagen import (
    GoogleImagenError,
    _extract_first_image_bytes,
    _http_error_message,
    _predictions_debug_summary,
    build_imagen_predict_parameters,
)
from app.services.slide_image_plan import build_slide_image_jobs

logger = logging.getLogger(__name__)

_CLOUD_PLATFORM_SCOPE = ("https://www.googleapis.com/auth/cloud-platform",)


def response_indicates_try_next_region(resp: httpx.Response) -> bool:
    """True when another Vertex region may succeed (quota / rate / overload)."""
    if resp.status_code == 429:
        return True
    if resp.status_code == 503:
        return True
    if resp.status_code not in (200, 400, 403, 404, 500, 502, 504):
        return False
    try:
        j = resp.json()
        err = j.get("error")
        if not isinstance(err, dict):
            return False
        status = str(err.get("status", "") or "").upper()
        msg = str(err.get("message", "") or "").lower()
        if "RESOURCE_EXHAUSTED" in status or "resource exhausted" in msg:
            return True
        if "quota" in msg:
            return True
        if "rate" in msg and "exceed" in msg:
            return True
        if "too many requests" in msg:
            return True
    except Exception:
        pass
    return False


def _credentials_path(settings: Settings) -> str:
    p = (settings.google_tts_credentials_json_path or "").strip()
    if p:
        expanded = Path(p).expanduser()
        if expanded.is_file():
            return str(expanded.resolve())
    adc = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if adc:
        expanded = Path(adc).expanduser()
        if expanded.is_file():
            return str(expanded.resolve())
    return ""


def _access_token_sync(credentials_path: str) -> str:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as e:
        raise GoogleImagenError(
            "google-auth is required for Vertex Imagen. Install: pip install google-auth"
        ) from e

    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=_CLOUD_PLATFORM_SCOPE,
    )
    creds.refresh(Request())
    token = creds.token
    if not token:
        raise GoogleImagenError("GCP credentials refresh returned no access token")
    return token


def _vertex_regions(settings: Settings) -> list[str]:
    raw = (settings.vertex_imagen_regions or "").strip()
    if not raw:
        return []
    return [r.strip() for r in raw.split(",") if r.strip()]


def _predict_url(project: str, region: str, model: str) -> str:
    return (
        f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{region}/publishers/google/models/{model}:predict"
    )


async def _generate_one_vertex_region(
    client: httpx.AsyncClient,
    settings: Settings,
    credentials_path: str,
    project: str,
    region: str,
    model: str,
    prompt: str,
    out_path: Path,
) -> bool:
    """POST to one region. Returns True if image written."""
    url = _predict_url(project, region, model)
    body: dict[str, Any] = {
        "instances": [{"prompt": prompt}],
        "parameters": build_imagen_predict_parameters(settings, vertex=True),
    }

    token = await asyncio.to_thread(_access_token_sync, credentials_path)
    resp = await client.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=body,
    )

    if response_indicates_try_next_region(resp):
        logger.warning(
            "Vertex Imagen region=%s HTTP %s (failover candidate): %s",
            region,
            resp.status_code,
            resp.text[:300],
        )
        return False

    if resp.status_code >= 400:
        raise GoogleImagenError(
            f"Vertex Imagen {region} error {resp.status_code}: {_http_error_message(resp)}"
        )

    try:
        data = resp.json()
    except Exception as e:
        raise GoogleImagenError(f"Vertex Imagen {region}: invalid JSON") from e

    err = data.get("error")
    if isinstance(err, dict) and err.get("message"):
        raise GoogleImagenError(f"Vertex Imagen {region}: {err['message']}")

    raw = _extract_first_image_bytes(data)
    if not raw or len(raw) < 100:
        logger.warning(
            "Vertex Imagen %s: empty or tiny image. %s",
            region,
            _predictions_debug_summary(data),
        )
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    logger.info("Vertex Imagen ok region=%s out=%s", region, out_path.name)
    return True


async def _generate_one_with_region_failover(
    client: httpx.AsyncClient,
    settings: Settings,
    credentials_path: str,
    project: str,
    regions: list[str],
    model: str,
    prompt: str,
    out_path: Path,
) -> None:
    model = (model or "").strip()
    if not model:
        raise GoogleImagenError("IMAGEN_MODEL is empty")

    last_note = ""
    for region in regions:
        for attempt in range(3):
            if attempt > 0:
                delay = 2 ** (attempt - 1)
                logger.info(
                    "Vertex Imagen retry region=%s attempt=%s after %ss",
                    region,
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(delay)
            try:
                ok = await _generate_one_vertex_region(
                    client,
                    settings,
                    credentials_path,
                    project,
                    region,
                    model,
                    prompt,
                    out_path,
                )
                if ok:
                    return
                last_note = f"region {region} quota/rate or empty response"
                break
            except httpx.RequestError as e:
                last_note = str(e)
                if attempt == 2:
                    logger.warning("Vertex Imagen region=%s network error: %s", region, e)
                    break
                continue

    raise GoogleImagenError(
        "Vertex Imagen failed in all configured regions (quota, network, or empty image). "
        f"Last: {last_note}. Regions tried: {', '.join(regions)}"
    )


async def generate_vertex_imagen_slide_images(
    settings: Settings,
    topic: str,
    script: ScriptPayload,
    language: LanguageCode,
    slides_dir: Path,
    *,
    reserve_product_hero_zone: bool = False,
) -> list[Path]:
    if not settings.vertex_imagen_configured():
        raise GoogleImagenError(
            "Vertex Imagen is not configured (VERTEX_IMAGEN_PROJECT / GOOGLE_CLOUD_PROJECT, "
            "service account JSON via GOOGLE_TTS_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS, "
            "and IMAGEN_USE_VERTEX or Vertex Gemini 2.5 image failover enabled)"
        )

    credentials_path = _credentials_path(settings)
    if not credentials_path:
        raise GoogleImagenError(
            "No GCP service account JSON for Vertex "
            "(GOOGLE_TTS_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS)"
        )

    project = (settings.vertex_imagen_project_id or "").strip()
    regions = _vertex_regions(settings)
    if not regions:
        raise GoogleImagenError("VERTEX_IMAGEN_REGIONS is empty")

    slides_dir.mkdir(parents=True, exist_ok=True)
    eff_model = settings.imagen_model_effective()
    logger.info("Vertex Imagen using model=%s (IMAGEN_MODEL raw=%r)", eff_model, (settings.imagen_model or "").strip())
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
                await _generate_one_with_region_failover(
                    client,
                    settings,
                    credentials_path,
                    project,
                    regions,
                    eff_model,
                    p,
                    out,
                )

        await asyncio.gather(*[_run(j.prompt, j.output_path) for j in jobs])

    paths = [j.output_path for j in jobs]

    missing = [p for p in paths if not p.is_file() or p.stat().st_size < 100]
    if missing:
        raise GoogleImagenError(f"Missing or empty slides: {[m.name for m in missing]}")

    return paths
