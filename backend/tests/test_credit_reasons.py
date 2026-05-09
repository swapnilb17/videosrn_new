"""Unit tests for app.credit_reasons helpers (used by Usage report + admin feed)."""

from __future__ import annotations

from app.credit_reasons import (
    REASON_KIND,
    REASON_LABEL,
    classify_reason,
    query_type_for,
    usage_unit,
    usage_user_query,
)


def test_known_reasons_have_label_and_kind():
    for reason, kind in REASON_KIND.items():
        assert kind in {"grant", "spend", "refund"}, reason
        assert reason in REASON_LABEL, reason


def test_classify_unknown_reason_falls_back_to_sign():
    kind, label = classify_reason("totally_new_reason", -10)
    assert kind == "spend"
    assert label == "Totally New Reason"

    kind2, label2 = classify_reason("brand_new_grant", 25)
    assert kind2 == "grant"
    assert label2 == "Brand New Grant"


def test_classify_known_reasons():
    assert classify_reason("standard_video", -45)[0] == "spend"
    assert classify_reason("signup_grant", 50)[0] == "grant"
    assert classify_reason("refund_failed_job", 45)[0] == "refund"


def test_query_type_for_known_reasons():
    assert query_type_for("standard_video") == "Topic → Video"
    assert query_type_for("generate_image") == "Image"
    assert query_type_for("tts_generate") == "Voice"


def test_query_type_for_unknown_reason_uses_label():
    assert query_type_for("custom_reason_x") == "Custom Reason X"


def test_usage_unit_standard_video():
    count, label = usage_unit("standard_video", {"target_sec": 59})
    assert count == 59
    assert label == "59 sec"


def test_usage_unit_image_pluralizes():
    assert usage_unit("generate_image", {"count": 1}) == (1, "1 image")
    assert usage_unit("generate_image", {"count": 4}) == (4, "4 images")


def test_usage_unit_tts_formats_thousands():
    count, label = usage_unit("tts_generate", {"chars": 1820})
    assert count == 1820
    assert "1,820" in label


def test_usage_unit_veo_includes_tier():
    count, label = usage_unit(
        "veo_image_to_ad",
        {"duration_sec": 8, "tier": "1080"},
    )
    assert count == 8
    assert "1080p" in label


def test_usage_unit_handles_missing_meta():
    count, label = usage_unit("standard_video", None)
    assert count is None
    assert label == "—"


def test_usage_user_query_prefers_topic():
    s = usage_user_query(
        "standard_video",
        {"topic": "How transformers work", "job_id": "abc"},
    )
    assert s == "How transformers work"


def test_usage_user_query_prompt_truncated():
    long = "x" * 500
    s = usage_user_query("generate_image", {"prompt": long})
    assert s.endswith("…")
    assert len(s) <= 200


def test_usage_user_query_grant_label():
    assert usage_user_query("signup_grant", {}) == "Welcome bonus"
    s = usage_user_query("admin_credit_code", {"code": "ENABLY1000"})
    assert "ENABLY1000" in s
