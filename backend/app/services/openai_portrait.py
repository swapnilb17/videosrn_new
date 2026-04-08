"""Portrait stylisation via OpenAI images.edit with model dall-e-2 only.

OpenAI's images.edit endpoint returns 400 for gpt-image-1 on many API keys; Settings
coerces OPENAI_IMAGE_EDIT_MODEL to dall-e-2 at load time.
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


# dall-e-2 images.edit: square sizes only; we use 1024x1024 for all aspects.
_DALLE2_EDIT_SIZE = "1024x1024"
_DALLE2_PROMPT_MAX = 1000


def _edit_prompt_for_dalle2(prompt: str) -> str:
    if len(prompt) > _DALLE2_PROMPT_MAX:
        logger.warning(
            "Truncating portrait prompt from %s to %s chars for dall-e-2",
            len(prompt),
            _DALLE2_PROMPT_MAX,
        )
        return prompt[: _DALLE2_PROMPT_MAX - 1] + "…"
    return prompt


async def generate_openai_portrait(
    api_key: str,
    image_bytes: bytes,
    prompt: str,
    out_path: Path,
    *,
    model: str = "dall-e-2",
    aspect_ratio: str = "1:1",
    timeout: float = 120.0,
) -> None:
    """Call OpenAI images.edit (dall-e-2) with the user's photo and style prompt.

    *model* is ignored unless it is dall-e-2 (defensive); callers should pass settings value.
    *aspect_ratio* is accepted for API compatibility; dall-e-2 edit only supports square output.
    """
    if not api_key:
        raise OpenAIPortraitError("OPENAI_API_KEY is not set")

    mid = (model or "dall-e-2").strip().lower() or "dall-e-2"
    if mid != "dall-e-2":
        logger.warning("images.edit ignoring model %r; using dall-e-2", model)
        mid = "dall-e-2"

    prompt_use = _edit_prompt_for_dalle2(prompt)
    client = AsyncOpenAI(api_key=api_key, timeout=timeout)

    try:
        image_file = io.BytesIO(image_bytes)
        image_file.name = "photo.png"

        response = await client.images.edit(
            model=mid,
            image=image_file,
            prompt=prompt_use,
            size=_DALLE2_EDIT_SIZE,
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
