"""Unit tests for OpenAI portrait edit helpers."""

from app.services.openai_portrait import _edit_prompt, _edit_size


def test_edit_size_dalle2_always_square():
    assert _edit_size("dall-e-2", "9:16") == "1024x1024"
    assert _edit_size("dall-e-2", "16:9") == "1024x1024"


def test_edit_size_gpt_image_uses_aspect():
    assert _edit_size("gpt-image-1", "9:16") == "1024x1536"


def test_edit_prompt_dalle2_truncates():
    long_p = "x" * 1200
    out = _edit_prompt("dall-e-2", long_p)
    assert len(out) == 1000
    assert out.endswith("…")


def test_edit_prompt_gpt_image_untruncated():
    long_p = "x" * 1200
    assert _edit_prompt("gpt-image-1", long_p) == long_p
