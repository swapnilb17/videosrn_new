"""
Decide which slide segments should feature the user's product (in-hand or composited).

Image backends should not duplicate this logic: use ``app.services.slide_image_plan.build_slide_image_jobs``.
"""

from __future__ import annotations

import re
from typing import Sequence

# English cues that the scene is about the retail product, purchase, or kitchen use.
_PRODUCTISH = re.compile(
    r"\b(product|products|bottle|bottles|jar|jars|oil|oils|package|packaging|pack|"
    r"label|labels|brand|brands|buy|purchase|shopping|shop|store|stores|price|prices|"
    r"offer|offers|ingredient|ingredients|pour|pouring|cook|cooking|recipe|recipes|"
    r"kitchen|stove|pan|fry|serve|serving|quality|premium|natural|organic|cold[- ]?pressed|"
    r"healthy|health|benefit|benefits|vitamin|supplement|nutrient|nutrients|"
    r"counter|shelf|shelves|carton|container|cap|seal|sealed|ml\b|liter|litre|ounce|oz\b)\b",
    re.I,
)


def _topic_tokens(topic: str) -> frozenset[str]:
    t = re.sub(r"[^\w\s]", " ", (topic or "").lower())
    return frozenset(w for w in t.split() if len(w) > 2)


def _blob(narration: str, hint: str | None) -> str:
    return f"{narration or ''} {(hint or '')}".lower()


def slide_should_show_user_product(
    topic: str,
    segment_id: str,
    narration: str,
    visual_hint_en: str | None,
    *,
    is_last_segment: bool,
) -> bool:
    """Heuristic: show product on CTA/outro, or when copy/visual clearly concerns the product."""
    if is_last_segment:
        return True
    if segment_id == "ending":
        return True
    b = _blob(narration, visual_hint_en)
    if _PRODUCTISH.search(b):
        return True
    for tok in _topic_tokens(topic):
        if re.search(rf"\b{re.escape(tok)}\b", b):
            return True
    return False


def product_visibility_per_segment(
    topic: str,
    segments: Sequence[tuple[str, str]],
    hints: Sequence[str | None] | None,
) -> list[bool]:
    """
    One bool per segment (same order as script_visual_segments), True = include user product on this slide.
    If nothing matches, enable first and last only so the product still appears in a typical ad arc.
    """
    hints_list = list(hints) if hints is not None else []
    n = len(segments)
    out: list[bool] = []
    for i, (seg_id, text) in enumerate(segments):
        hint = hints_list[i] if i < len(hints_list) else None
        out.append(
            slide_should_show_user_product(
                topic,
                seg_id,
                text,
                hint,
                is_last_segment=(i == n - 1),
            )
        )
    if n and not any(out):
        out[0] = True
        out[-1] = True
    return out


def visibility_by_slide_stem(
    topic: str,
    segments: Sequence[tuple[str, str]],
    hints: Sequence[str | None] | None,
) -> dict[str, bool]:
    """Map slide filename stem (segment id) -> show product."""
    flags = product_visibility_per_segment(topic, segments, hints)
    return {seg_id: flags[i] for i, (seg_id, _) in enumerate(segments)}
