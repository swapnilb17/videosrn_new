"""
Single planning API for script-based slide images and user-product placement.

Adding a new image backend
--------------------------
1. Call :func:`build_slide_image_jobs` with ``topic``, ``script``, ``language``,
   ``slides_dir``, plus ``reserve_product_hero_zone`` and ``product_reference_path``
   exactly like the existing generators.
2. For each returned :class:`SlideImageJob`, generate one image:
   - Use ``job.prompt`` as the text prompt.
   - If ``job.reference_png_bytes`` is set, attach it as the user-product reference
     (multimodal / in-hand), matching Gemini and Vertex Gemini behavior.
   - If ``job.reserve_product_hero_zone`` is true, the prompt already asks the model
     to leave the compositing corner clear (Imagen-style pipelines).
3. If you composite a product PNG after generation (no in-model reference), only
   composite slides where :func:`visibility_by_slide_stem` is true for that slide's
   filename stem — same as ``app.main`` does for Imagen/Nano.

Tweaking *when* the product appears is done only in
``app.services.product_slide_policy``; new models should not reimplement that logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.schemas import LanguageCode, ScriptPayload
from app.services.image_prompts import build_slide_image_prompt, script_visual_segments
from app.services.product_slide_policy import (
    product_visibility_per_segment,
    visibility_by_slide_stem,
)

__all__ = [
    "SlideImageJob",
    "build_slide_image_jobs",
    "product_visibility_per_segment",
    "visibility_by_slide_stem",
]


@dataclass(frozen=True)
class SlideImageJob:
    """One slide file to generate; field meanings match existing backends."""

    segment_id: str
    output_path: Path
    prompt: str
    reference_png_bytes: bytes | None
    reserve_product_hero_zone: bool


def build_slide_image_jobs(
    topic: str,
    script: ScriptPayload,
    language: LanguageCode,
    slides_dir: Path,
    *,
    reserve_product_hero_zone: bool = False,
    product_reference_path: Path | None = None,
) -> list[SlideImageJob]:
    """
    Build per-slide prompts and multimodal/compositing flags.

    ``reserve_product_hero_zone`` is the global switch from ``app.main`` (product on
    but no reference image, or Imagen/Nano compositing). When a reference file exists,
    per-slide reference bytes are still gated by the product policy.
    """
    ref_bytes: bytes | None = None
    if product_reference_path is not None and product_reference_path.is_file():
        ref_bytes = product_reference_path.read_bytes()

    segments = script_visual_segments(script)
    hints = script.visual_segments_en
    show_flags = (
        product_visibility_per_segment(topic, segments, hints)
        if (ref_bytes or reserve_product_hero_zone)
        else [False] * len(segments)
    )

    slides_dir = Path(slides_dir)
    jobs: list[SlideImageJob] = []
    for i, (seg_id, text) in enumerate(segments):
        hint = hints[i] if i < len(hints) else None
        use_ref_here = bool(ref_bytes and show_flags[i])
        reserve_here = (
            reserve_product_hero_zone and not use_ref_here and show_flags[i]
        )
        jobs.append(
            SlideImageJob(
                segment_id=seg_id,
                output_path=slides_dir / f"{seg_id}.png",
                prompt=build_slide_image_prompt(
                    topic,
                    text,
                    language,
                    visual_hint_en=hint,
                    reserve_product_hero_zone=reserve_here,
                    user_product_reference=use_ref_here,
                ),
                reference_png_bytes=ref_bytes if use_ref_here else None,
                reserve_product_hero_zone=reserve_here,
            )
        )
    return jobs
