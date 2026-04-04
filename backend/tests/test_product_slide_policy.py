"""Tests for product slide visibility heuristics."""

from app.services.product_slide_policy import (
    product_visibility_per_segment,
    slide_should_show_user_product,
    visibility_by_slide_stem,
)


def test_last_segment_always_shows():
    assert slide_should_show_user_product(
        "soap",
        "turn_1",
        "random lifestyle shot",
        None,
        is_last_segment=True,
    )


def test_ending_segment_id_shows_when_not_last_index():
    assert slide_should_show_user_product(
        "soap",
        "ending",
        "thanks",
        None,
        is_last_segment=False,
    )


def test_product_keyword_in_narration():
    assert slide_should_show_user_product(
        "xyz",
        "hook",
        "This premium bottle fits your kitchen.",
        None,
        is_last_segment=False,
    )


def test_topic_token_in_blob():
    assert slide_should_show_user_product(
        "organic honey",
        "hook",
        "Start your morning right with organic energy.",
        None,
        is_last_segment=False,
    )


def test_generic_copy_no_product():
    assert not slide_should_show_user_product(
        "organic honey",
        "turn_0",
        "Life moves fast. Take a breath.",
        "sunrise over hills, no objects",
        is_last_segment=False,
    )


def test_product_visibility_last_segment_always_on():
    """Final segment is always product-relevant (CTA/outro); middle slides can stay off."""
    segments = [("a", "abstract mood"), ("b", "still abstract"), ("c", "more abstract")]
    hints = [None, None, None]
    out = product_visibility_per_segment("widgets", segments, hints)
    assert out[-1] is True
    assert out[0] is False and out[1] is False
    assert len(out) == 3


def test_single_segment_counts_as_last():
    segments = [("only", "totally unrelated prose here")]
    hints = [None]
    out = product_visibility_per_segment("qq", segments, hints)
    assert out == [True]


def test_visibility_by_slide_stem_keys():
    segments = [("hook", "buy now"), ("outro", "bye")]
    m = visibility_by_slide_stem("x", segments, [None, None])
    assert m["hook"] is True
    assert m["outro"] is True
