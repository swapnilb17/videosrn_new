"""Portrait stylisation via OpenAI gpt-image-1 (images.edit).

Accepts a user photo + style prompt and returns the generated image bytes.
Used as the highest-priority tier for face-preserving portrait generation.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class OpenAIPortraitError(Exception):
    pass


ASPECT_TO_SIZE = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "4:3": "1024x1024",
}


async def generate_openai_portrait(
    api_key: str,
    image_bytes: bytes,
    prompt: str,
    out_path: Path,
    *,
    aspect_ratio: str = "1:1",
    timeout: float = 120.0,
) -> None:
    """Call OpenAI images.edit with the user's photo and style prompt.

    Writes the result PNG to *out_path*.  Raises OpenAIPortraitError on failure.
    """
    if not api_key:
        raise OpenAIPortraitError("OPENAI_API_KEY is not set")

    size = ASPECT_TO_SIZE.get(aspect_ratio, "1024x1024")

    client = AsyncOpenAI(api_key=api_key, timeout=timeout)

    try:
        image_file = io.BytesIO(image_bytes)
        image_file.name = "photo.png"

        response = await client.images.edit(
            model="gpt-image-1",
            image=image_file,
            prompt=prompt,
            size=size,
            quality="high",
            response_format="b64_json",
        )

        if not response.data or not response.data[0].b64_json:
            raise OpenAIPortraitError(
                "OpenAI returned empty image data (possible content filter)"
            )

        raw = base64.b64decode(response.data[0].b64_json)
        if len(raw) < 200:
            raise OpenAIPortraitError("OpenAI returned suspiciously small image")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw)
        logger.info("OpenAI portrait generation OK (%s bytes)", len(raw))

    except OpenAIPortraitError:
        raise
    except Exception as e:
        raise OpenAIPortraitError(f"OpenAI portrait failed: {e}") from e
    finally:
        await client.close()
