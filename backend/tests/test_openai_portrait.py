"""Unit tests for OpenAI portrait edit."""

import asyncio
from pathlib import Path

import pytest

from app.config import Settings
from app.services.openai_portrait import (
    OpenAIPortraitError,
    _edit_prompt_for_dalle2,
    generate_openai_portrait,
)


def test_edit_prompt_dalle2_truncates():
    long_p = "x" * 1200
    out = _edit_prompt_for_dalle2(long_p)
    assert len(out) == 1000
    assert out.endswith("…")


def test_openai_image_edit_model_env_coerced_to_dalle2(monkeypatch):
    monkeypatch.setenv("OPENAI_IMAGE_EDIT_MODEL", "gpt-image-1")
    s = Settings()
    assert s.openai_image_edit_model == "dall-e-2"


def test_generate_openai_portrait_requires_key():
    with pytest.raises(OpenAIPortraitError, match="OPENAI_API_KEY"):
        asyncio.run(
            generate_openai_portrait("", b"x", "hi", Path("/tmp/x.png")),
        )
