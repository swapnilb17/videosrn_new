"""Slide image prompts use English visual hints for hi/mr to reduce bad Devanagari in images."""

from app.services.image_prompts import build_slide_image_prompt


def test_hindi_uses_english_hint_not_narration():
    p = build_slide_image_prompt(
        "योग",
        "आपका स्वास्थ्य महत्वपूर्ण है",
        "hi",
        visual_hint_en="Woman meditating on a yoga mat in a sunlit room, peaceful mood.",
    )
    assert "Woman meditating" in p
    assert "आपका" not in p
    assert "Devanagari" in p or "Indic" in p


def test_english_falls_back_to_narration_without_hint():
    p = build_slide_image_prompt("Photosynthesis", "Plants use sunlight.", "en", visual_hint_en=None)
    assert "Plants use sunlight" in p


def test_reserve_product_zone_adds_lower_left_instruction():
    p = build_slide_image_prompt(
        "Oil",
        "Healthy cooking.",
        "en",
        visual_hint_en="Kitchen counter with vegetables.",
        reserve_product_hero_zone=True,
    )
    assert "lower-left" in p.lower() or "RESERVED" in p
    assert "overlay" in p.lower() or "composited" in p.lower()


def test_user_product_reference_asks_for_in_hand_hero():
    p = build_slide_image_prompt(
        "Oil",
        "Chef in kitchen.",
        "en",
        visual_hint_en="Warm kitchen with stove.",
        user_product_reference=True,
    )
    assert "attached image" in p
    assert "holding" in p.lower() or "hold" in p.lower()
    assert "picture-in-picture" in p.lower() or "inset" in p.lower()
