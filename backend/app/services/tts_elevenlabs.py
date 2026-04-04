import asyncio
import logging
from pathlib import Path

import httpx

from app.config import Settings
from app.schemas import LanguageCode

logger = logging.getLogger(__name__)

ELEVEN_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsError(Exception):
    pass


async def synthesize_elevenlabs(
    settings: Settings,
    text: str,
    language: LanguageCode,
    out_mp3: Path,
    max_attempts: int = 4,
) -> None:
    api_key = (settings.elevenlabs_api_key or "").strip()
    voice_id = settings.elevenlabs_voice_for_language(language)
    if not api_key or not voice_id:
        raise ElevenLabsError("ElevenLabs API key or voice id not configured")

    url = f"{ELEVEN_BASE}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    body = {
        "text": text,
        "model_id": settings.elevenlabs_model_id,
    }

    last_err: Exception | None = None
    delay = 1.0
    async with httpx.AsyncClient(timeout=settings.elevenlabs_timeout) as client:
        for attempt in range(max_attempts):
            try:
                resp = await client.post(url, json=body, headers=headers)
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = httpx.HTTPStatusError(
                        "retryable",
                        request=resp.request,
                        response=resp,
                    )
                    if attempt == max_attempts - 1:
                        break
                    logger.info(
                        "ElevenLabs HTTP %s, retrying in %.1fs",
                        resp.status_code,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 16.0)
                    continue
                resp.raise_for_status()
                out_mp3.parent.mkdir(parents=True, exist_ok=True)
                out_mp3.write_bytes(resp.content)
                return
            except httpx.TimeoutException as e:
                last_err = e
                if attempt == max_attempts - 1:
                    break
                logger.info("ElevenLabs timeout, retrying in %.1fs", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 16.0)
            except httpx.NetworkError as e:
                last_err = e
                if attempt == max_attempts - 1:
                    break
                logger.info("ElevenLabs network error, retrying in %.1fs", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 16.0)
            except httpx.HTTPStatusError as e:
                last_err = e
                logger.warning("ElevenLabs non-retryable HTTP %s", e.response.status_code)
                break

    logger.exception("ElevenLabs TTS failed after retries: %s", last_err)
    raise ElevenLabsError("ElevenLabs TTS failed") from last_err
