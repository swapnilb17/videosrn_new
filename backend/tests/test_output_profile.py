from app.config import Settings
from app.output_profile import build_visual_settings_from_forms


def test_legacy_omits_both_returns_base_settings():
    base = Settings()
    out, cf, q = build_visual_settings_from_forms(base, "", "")
    assert out is base
    assert cf is None
    assert q is None


def test_youtube_1080p_dimensions_and_imagen_fields():
    base = Settings(video_width=320, video_height=180, imagen_aspect_ratio="9:16", imagen_image_size="1K")
    out, cf, q = build_visual_settings_from_forms(
        base, "youtube_landscape", "1080p"
    )
    assert cf == "youtube_landscape"
    assert q == "1080p"
    assert out.video_width == 1920
    assert out.video_height == 1080
    assert out.imagen_aspect_ratio == "16:9"
    assert out.imagen_image_size == "2K"


def test_reels_8k_square_pixels():
    base = Settings()
    out, cf, q = build_visual_settings_from_forms(base, "reels_shorts", "8k")
    assert out.video_width == 4320
    assert out.video_height == 7680
    assert out.imagen_aspect_ratio == "9:16"
    assert out.imagen_image_size == "4K"


def test_default_quality_when_only_format_sent():
    base = Settings()
    out, cf, q = build_visual_settings_from_forms(base, "instagram_fb", "")
    assert q == "1080p"
    assert out.video_width == 1080
    assert out.video_height == 1080


def test_default_format_when_only_quality_sent():
    base = Settings()
    out, cf, q = build_visual_settings_from_forms(base, "", "720p")
    assert cf == "reels_shorts"
    assert out.video_width == 720
    assert out.video_height == 1280
