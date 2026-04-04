import asyncio
import base64
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.schemas import LanguageCode, ScriptPayload
from app.services.slide_image_plan import build_slide_image_jobs

logger = logging.getLogger(__name__)


class NanoBananaError(Exception):
    pass


def _extract_url(data: dict[str, Any]) -> str | None:
    for key in ("url", "image_url", "output_url", "image", "result_url"):
        v = data.get(key)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v
    inner = data.get("data")
    if isinstance(inner, dict):
        u = _extract_url(inner)
        if u:
            return u
    if isinstance(inner, list) and inner:
        first = inner[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
        if isinstance(first, dict):
            u = _extract_url(first)
            if u:
                return u
    return None


def _extract_base64(data: dict[str, Any]) -> bytes | None:
    for key in ("image_base64", "b64_json", "image", "base64"):
        raw = data.get(key)
        if isinstance(raw, str) and len(raw) > 100:
            try:
                if raw.startswith("data:image"):
                    raw = raw.split(",", 1)[1]
                return base64.b64decode(raw, validate=False)
            except Exception:
                continue
    return None


def _normalize_api_base(raw: str) -> str:
    base = (raw or "").strip().rstrip("/")
    if not base:
        raise NanoBananaError("NANO_BANANA_BASE_URL is empty")
    if "://" not in base:
        base = "https://" + base
    parsed = urlparse(base)
    if not parsed.netloc:
        raise NanoBananaError(
            "NANO_BANANA_BASE_URL must include a hostname "
            "(e.g. https://api.bananapro.site — check for typos and stray spaces)."
        )
    return base


async def _generate_one(
    client: httpx.AsyncClient,
    settings: Settings,
    prompt: str,
    out_path: Path,
) -> None:
    base = _normalize_api_base(settings.nano_banana_base_url)
    url = f"{base}/v1/generate"
    headers = {
        "Authorization": f"Bearer {settings.nano_banana_api_key}",
        "Content-Type": "application/json",
    }
    vw, vh = settings.video_width, settings.video_height
    max_side = 1920
    if vw > 0 and vh > 0 and (vw > max_side or vh > max_side):
        s = min(max_side / vw, max_side / vh)
        rw = max(64, int(round(vw * s)))
        rh = max(64, int(round(vh * s)))
    else:
        rw, rh = max(64, vw), max(64, vh)
    body: dict[str, Any] = {
        "prompt": prompt,
        "width": rw,
        "height": rh,
        "style": settings.nano_banana_style,
        "negative_prompt": (
            "blurry, low quality, distorted, nsfw, watermark, logo, "
            "text overlay, subtitles, ugly typography, extra limbs"
        ),
        "steps": settings.nano_banana_steps,
        "guidance_scale": settings.nano_banana_guidance,
    }

    try:
        resp = await client.post(url, json=body, headers=headers)
    except httpx.RequestError as e:
        raise NanoBananaError(
            f"Cannot reach image API ({base!r}): {e}. "
            "Fix NANO_BANANA_BASE_URL in .env to match your provider’s API host."
        ) from e

    if resp.status_code >= 400:
        logger.warning("Nano Banana HTTP %s: %s", resp.status_code, resp.text[:500])
        raise NanoBananaError(f"API error {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:
        raise NanoBananaError("Invalid JSON from image API") from e

    img_url = _extract_url(data)
    if img_url:
        try:
            dl = await client.get(img_url, follow_redirects=True)
            dl.raise_for_status()
        except httpx.RequestError as e:
            raise NanoBananaError(f"Failed to download generated image: {e}") from e
        except httpx.HTTPStatusError as e:
            raise NanoBananaError(
                f"Image download failed with HTTP {e.response.status_code}"
            ) from e
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(dl.content)
        return

    raw = _extract_base64(data)
    if raw:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw)
        return

    raise NanoBananaError("Response had no image URL or base64 payload")


async def generate_slide_images(
    settings: Settings,
    topic: str,
    script: ScriptPayload,
    language: LanguageCode,
    slides_dir: Path,
    *,
    reserve_product_hero_zone: bool = False,
) -> list[Path]:
    if not (settings.nano_banana_api_key or "").strip():
        raise NanoBananaError("NANO_BANANA_API_KEY is not set")

    slides_dir.mkdir(parents=True, exist_ok=True)
    jobs = build_slide_image_jobs(
        topic,
        script,
        language,
        slides_dir,
        reserve_product_hero_zone=reserve_product_hero_zone,
        product_reference_path=None,
    )

    sem = asyncio.Semaphore(max(1, settings.nano_banana_max_concurrent))

    async with httpx.AsyncClient(timeout=settings.nano_banana_timeout) as client:

        async def _run(p: str, out: Path) -> None:
            async with sem:
                await _generate_one(client, settings, p, out)

        await asyncio.gather(*[_run(j.prompt, j.output_path) for j in jobs])

    paths = [j.output_path for j in jobs]

    missing = [p for p in paths if not p.is_file() or p.stat().st_size < 100]
    if missing:
        raise NanoBananaError(f"Missing or empty slides: {[m.name for m in missing]}")

    return paths
