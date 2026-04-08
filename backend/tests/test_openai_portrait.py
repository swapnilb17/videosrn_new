"""Unit tests for OpenAI portrait edit helpers."""

from app.services.openai_portrait import (
    _edit_prompt,
    _edit_size,
    _images_edit_model_rejected_use_dalle2,
)


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


def test_images_edit_model_rejected_detection():
    exc_msg = (
        "Error code: 400 - {'error': {'message': \"Invalid value: 'gpt-image-1'. "
        "Value must be 'dall-e-2'.\", 'param': 'model', 'code': 'invalid_value'}}"
    )
    assert _images_edit_model_rejected_use_dalle2(RuntimeError(exc_msg), "gpt-image-1") is True
    assert _images_edit_model_rejected_use_dalle2(RuntimeError(exc_msg), "dall-e-2") is False
    assert _images_edit_model_rejected_use_dalle2(RuntimeError("network down"), "gpt-image-1") is False
