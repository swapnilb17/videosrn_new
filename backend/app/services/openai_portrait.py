"""Portrait stylisation via OpenAI images.edit (dall-e-2 or gpt-image-1 per OPENAI_IMAGE_EDIT_MODEL).

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

# dall-e-2 images.edit only allows these sizes (square).
_DALLE2_EDIT_SIZE = "1024x1024"
_DALLE2_PROMPT_MAX = 1000


def _edit_size(model: str, aspect_ratio: str) -> str:
    m = (model or "").strip().lower()
    if m == "dall-e-2" or m.startswith("dall-e-2"):
        return _DALLE2_EDIT_SIZE
    return ASPECT_TO_SIZE.get(aspect_ratio, "1024x1024")


def _edit_prompt(model: str, prompt: str) -> str:
    m = (model or "").strip().lower()
    if m == "dall-e-2" or m.startswith("dall-e-2"):
        if len(prompt) > _DALLE2_PROMPT_MAX:
            logger.warning(
                "Truncating portrait prompt from %s to %s chars for dall-e-2",
                len(prompt),
                _DALLE2_PROMPT_MAX,
            )
            return prompt[: _DALLE2_PROMPT_MAX - 1] + "…"
    return prompt


def _images_edit_model_rejected_use_dalle2(exc: BaseException, attempted_model: str) -> bool:
    """True when OpenAI only allows dall-e-2 on images.edit (common for many API keys)."""
    if (attempted_model or "").strip().lower() in ("", "dall-e-2"):
        return False
    msg = str(exc).lower()
    if "invalid_value" not in msg and "invalid request" not in msg:
        return False
    return "dall-e-2" in msg and ("model" in msg or "param" in msg or "gpt-image" in msg)


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
    """Call OpenAI images.edit with the user's photo and style prompt.

    Writes the result PNG to *out_path*.  Raises OpenAIPortraitError on failure.
    """
    if not api_key:
        raise OpenAIPortraitError("OPENAI_API_KEY is not set")

    model_id = (model or "dall-e-2").strip() or "dall-e-2"
    client = AsyncOpenAI(api_key=api_key, timeout=timeout)

    try:
        attempt_models = [model_id]
        if model_id != "dall-e-2":
            attempt_models.append("dall-e-2")

        for i, mid in enumerate(attempt_models):
            try:
                size = _edit_size(mid, aspect_ratio)
                prompt_use = _edit_prompt(mid, prompt)
                image_file = io.BytesIO(image_bytes)
                image_file.name = "photo.png"

                response = await client.images.edit(
                    model=mid,
                    image=image_file,
                    prompt=prompt_use,
                    size=size,
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
                if i > 0:
                    logger.info(
                        "OpenAI portrait OK with dall-e-2 fallback after %r was rejected (%s bytes)",
                        model_id,
                        len(raw),
                    )
                else:
                    logger.info("OpenAI portrait generation OK (%s bytes)", len(raw))
                return

            except OpenAIPortraitError:
                raise
            except Exception as e:
                if (
                    i == 0
                    and len(attempt_models) > 1
                    and _images_edit_model_rejected_use_dalle2(e, model_id)
                ):
                    logger.warning(
                        "OpenAI images.edit rejected model %r (%s); retrying with dall-e-2",
                        model_id,
                        e,
                    )
                    continue
                raise OpenAIPortraitError(f"OpenAI portrait failed: {e}") from e

    finally:
        await client.close()
