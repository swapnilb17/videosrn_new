"""Contract tests for the shared slide + product planner (new backends should use this)."""

from pathlib import Path

from app.schemas import ScriptPayload
from app.services.slide_image_plan import SlideImageJob, build_slide_image_jobs


def _minimal_script() -> ScriptPayload:
    return ScriptPayload(
        hook="Mood scene only.",
        facts=["Still no product words.", "More mood."],
        ending="Shop today.",
        full_script_plain="x",
        visual_segments_en=["sunrise", "hills", "valley", "hand holding shelf"],
    )


def test_build_slide_image_jobs_shape(tmp_path: Path):
    script = _minimal_script()
    slides = tmp_path / "slides"
    jobs = build_slide_image_jobs(
        "Test Topic",
        script,
        "en",
        slides,
        reserve_product_hero_zone=True,
        product_reference_path=None,
    )
    assert len(jobs) == 4
    assert all(isinstance(j, SlideImageJob) for j in jobs)
    assert jobs[0].segment_id == "hook"
    assert jobs[0].output_path == slides / "hook.png"
    assert jobs[0].reference_png_bytes is None
    # Last slide is always product-relevant
    assert jobs[-1].reserve_product_hero_zone is True


def test_multimodal_reference_only_on_flagged_slides(tmp_path: Path):
    script = _minimal_script()
    ref = tmp_path / "p.png"
    ref.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    jobs = build_slide_image_jobs(
        "Test Topic",
        script,
        "en",
        tmp_path / "slides",
        reserve_product_hero_zone=False,
        product_reference_path=ref,
    )
    assert jobs[0].reference_png_bytes is None
    assert jobs[-1].reference_png_bytes is not None
    assert jobs[-1].reserve_product_hero_zone is False
