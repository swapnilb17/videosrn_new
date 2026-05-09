"""Shared catalogue of `credit_ledger.reason` values + UX helpers.

Used by:
  * the admin Activity feed (`routers/internal_admin.py`)
  * the per-user Usage report (`/internal/credits/me/usage`)

Adding a new `reason=` anywhere in the app? Add it to:
  * :data:`REASON_KIND`   — for the grant/spend/refund classification.
  * :data:`REASON_LABEL`  — for a humanised label.
  * :data:`REASON_QUERY_TYPE` — short label rendered in the user-facing
    "Query Type" column. Defaults to the humanised label otherwise.

Unknown reasons still render fine: kind defaults to grant/spend by sign of
``delta`` and label is a Title-cased version of the reason.
"""

from __future__ import annotations

from typing import Any


REASON_KIND: dict[str, str] = {
    "signup_grant": "grant",
    "starter_redeem_grant": "grant",
    "promo_code_grant": "grant",
    "admin_credit_code": "grant",
    "razorpay_starter_purchase": "grant",
    "refund_failed_job": "refund",
    "refund_veo_failed": "refund",
    "standard_video": "spend",
    "generate_image": "spend",
    "veo_image_to_ad": "spend",
    "veo_text_to_video": "spend",
    "veo_photo_to_video": "spend",
    "veo_frame_to_video": "spend",
    "kling_text_to_video": "spend",
    "kling_photo_to_video": "spend",
    "tts_generate": "spend",
}

REASON_LABEL: dict[str, str] = {
    "signup_grant": "Signup credits",
    "starter_redeem_grant": "Starter unlocked",
    "promo_code_grant": "Legacy promo redeemed",
    "admin_credit_code": "Admin code redeemed",
    "razorpay_starter_purchase": "Razorpay payment captured",
    "refund_failed_job": "Refund (failed job)",
    "refund_veo_failed": "Refund (Veo failed)",
    "standard_video": "Standard video",
    "generate_image": "Image generated",
    "veo_image_to_ad": "Veo image-to-ad",
    "veo_text_to_video": "Veo text-to-video",
    "veo_photo_to_video": "Veo photo-to-video",
    "veo_frame_to_video": "Veo frame-to-video",
    "kling_text_to_video": "Kling text-to-video",
    "kling_photo_to_video": "Kling photo-to-video",
    "tts_generate": "TTS generated",
}

# Short, user-facing column value (Settings → Usage report → "Query Type").
# Optional: any reason not listed here falls back to REASON_LABEL.
REASON_QUERY_TYPE: dict[str, str] = {
    "standard_video": "Topic → Video",
    "generate_image": "Image",
    "tts_generate": "Voice",
    "veo_image_to_ad": "Veo (image-to-ad)",
    "veo_text_to_video": "Veo (text-to-video)",
    "veo_photo_to_video": "Veo (photo-to-video)",
    "veo_frame_to_video": "Veo (frame-to-video)",
    "kling_text_to_video": "Kling (text-to-video)",
    "kling_photo_to_video": "Kling (photo-to-video)",
    "signup_grant": "Welcome bonus",
    "starter_redeem_grant": "Starter unlocked",
    "promo_code_grant": "Promo code",
    "admin_credit_code": "Credit code",
    "razorpay_starter_purchase": "Purchase",
    "refund_failed_job": "Refund (failed job)",
    "refund_veo_failed": "Refund (Veo failed)",
}


def classify_reason(reason: str, delta: int) -> tuple[str, str]:
    """Return ``(kind, label)`` for a ledger row.

    ``kind`` is one of ``grant`` / ``spend`` / ``refund`` / ``other``.
    Unknown reasons fall back to the sign of ``delta`` and a Title-cased label.
    """
    kind = REASON_KIND.get(reason)
    if kind is None:
        kind = "grant" if delta >= 0 else "spend"
    label = REASON_LABEL.get(reason, (reason or "").replace("_", " ").title() or "Activity")
    return kind, label


def query_type_for(reason: str) -> str:
    """Short user-facing string for the Settings usage report's `Query Type` column."""
    if reason in REASON_QUERY_TYPE:
        return REASON_QUERY_TYPE[reason]
    return REASON_LABEL.get(reason, (reason or "").replace("_", " ").title() or "Activity")


def _coerce_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else None
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            try:
                return int(s)
            except ValueError:
                return None
    return None


def usage_unit(
    reason: str,
    meta: dict[str, Any] | None,
) -> tuple[int | None, str]:
    """Return ``(count_or_seconds, label)`` for the "Count / Per sec" column.

    The count is a numeric for sorting/filtering; the label is the human string
    rendered next to it (e.g. ``"59 sec"`` or ``"4 images"``). Both fall back
    gracefully when the expected meta fields are missing.
    """
    m: dict[str, Any] = meta or {}

    if reason == "standard_video":
        sec = _coerce_int(m.get("target_sec"))
        return sec, f"{sec} sec" if sec is not None else "—"

    if reason == "generate_image":
        c = _coerce_int(m.get("count")) or 1
        unit = "image" if c == 1 else "images"
        return c, f"{c} {unit}"

    if reason == "tts_generate":
        ch = _coerce_int(m.get("chars"))
        return ch, f"{ch:,} chars" if ch is not None else "—"

    if reason in {
        "veo_image_to_ad",
        "veo_text_to_video",
        "veo_photo_to_video",
        "veo_frame_to_video",
        "kling_text_to_video",
        "kling_photo_to_video",
    }:
        sec = _coerce_int(m.get("duration_sec"))
        tier = str(m.get("tier") or "").strip()
        if sec is not None and tier:
            return sec, f"{sec} sec @ {tier}p"
        if sec is not None:
            return sec, f"{sec} sec"
        return None, "—"

    return None, "—"


def usage_user_query(reason: str, meta: dict[str, Any] | None) -> str:
    """Best-effort "User Query" cell for a ledger row.

    Prefers a real prompt/topic in ``meta`` (e.g. ``meta['topic']`` for
    standard video, ``meta['prompt']`` for image / Veo). Falls back to a
    short, neutral string for grants / refunds.
    """
    m: dict[str, Any] = meta or {}

    for key in ("topic", "prompt", "ad_copy", "text", "title"):
        raw = m.get(key)
        if isinstance(raw, str):
            s = raw.strip()
            if s:
                return s if len(s) <= 200 else s[:197] + "…"

    if reason == "razorpay_starter_purchase":
        return "Starter bundle (₹499)"
    if reason in {"promo_code_grant", "admin_credit_code"}:
        code = m.get("code")
        if isinstance(code, str) and code.strip():
            return f"Code: {code.strip()}"
        return "Credit code"
    if reason == "starter_redeem_grant":
        return "Starter invite redeemed"
    if reason == "signup_grant":
        return "Welcome bonus"
    if reason in {"refund_failed_job", "refund_veo_failed"}:
        job_id = m.get("job_id")
        if isinstance(job_id, str) and job_id.strip():
            return f"Refund · {job_id.strip()[:24]}"
        return "Refund"

    job_id = m.get("job_id")
    if isinstance(job_id, str) and job_id.strip():
        return job_id.strip()[:32]
    return "—"
