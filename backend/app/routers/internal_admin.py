"""Internal admin/observability read-only endpoints.

These routes are consumed by the separate `enably-admin` Next.js console
(BFF pattern). Trust model: caller must present the same
`x-internal-api-key` header that the existing `/internal/credits/*` routes
validate, so no new secret is introduced.

Design rules:
* Read-only. No writes, no side effects.
* Zero coupling with `main.py` internals (auth guard is re-implemented here
  so this file can be deleted or edited without touching the rest of the
  app). This is intentional to keep the blast radius minimal.
* Cheap queries only: simple indexed lookups + COUNT(*) with pagination.
  The BFF caches every response for 60s, so at most one call per minute
  per dataset hits the DB.
"""

from __future__ import annotations

import hmac
import logging
import re
import secrets
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.credit_service import normalize_redeem_code
from app.db import get_db_session
from app.models import (
    ContentTemplate,
    CreditCode,
    CreditLedger,
    RazorpayPayment,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/admin", tags=["internal-admin"])


# ---------------------------------------------------------------------------
# Auth guard (local copy of main._require_internal_api_key to avoid coupling)
# ---------------------------------------------------------------------------

def _load_settings() -> Settings:
    # Imported lazily so tests can patch app.main.load_settings if needed.
    from app.main import load_settings  # noqa: PLC0415

    return load_settings()


def _require_internal_api_key(request: Request) -> None:
    settings = _load_settings()
    secret = (settings.internal_api_secret or "").strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="INTERNAL_API_SECRET is not configured; /internal routes are disabled.",
        )
    hdr = (request.headers.get("x-internal-api-key") or "").strip()
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        hdr = auth[7:].strip() or hdr
    try:
        if not hmac.compare_digest(hdr, secret):
            raise HTTPException(status_code=401, detail="Invalid internal API credentials.")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid internal API credentials.") from None


def _require_db(session: AsyncSession | None) -> AsyncSession:
    if session is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    return session


# ---------------------------------------------------------------------------
# GET /internal/admin/health
# ---------------------------------------------------------------------------

@router.get("/health")
async def admin_health(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> dict[str, Any]:
    """Lightweight readiness check for the admin BFF.

    Pings the DB with `SELECT 1` so the Overview page can tell the operator
    at a glance whether the backend + DB path is healthy.
    """
    _require_internal_api_key(request)
    db = _require_db(session)
    try:
        await db.execute(select(1))
        db_ok = True
    except Exception:  # pragma: no cover - hard to simulate
        logger.exception("admin_health DB ping failed")
        db_ok = False
    return {"ok": db_ok, "version": "admin-v1"}


# ---------------------------------------------------------------------------
# GET /internal/admin/users
# ---------------------------------------------------------------------------

def _clamp_pagination(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))
    return page, page_size


@router.get("/users")
async def admin_list_users(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=320)] = None,
) -> dict[str, Any]:
    """Paginated snapshot of users + current credit balance.

    Sorted by newest signup first. Optional free-text filter `q` matches
    against `email` and `google_sub` (prefix + contains, case-insensitive).
    """
    _require_internal_api_key(request)
    db = _require_db(session)
    page, page_size = _clamp_pagination(page, page_size)

    base_filters = []
    q_clean = (q or "").strip()
    if q_clean:
        like = f"%{q_clean.lower()}%"
        base_filters.append(
            or_(
                func.lower(User.email).like(like),
                func.lower(func.coalesce(User.google_sub, "")).like(like),
            )
        )

    total_stmt = select(func.count()).select_from(User)
    if base_filters:
        total_stmt = total_stmt.where(*base_filters)
    total = int((await db.execute(total_stmt)).scalar() or 0)

    rows_stmt = (
        select(
            User.id,
            User.email,
            User.plan,
            User.credit_balance,
            User.starter_redeem_completed,
            User.created_at,
            User.updated_at,
        )
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if base_filters:
        rows_stmt = rows_stmt.where(*base_filters)

    rows = (await db.execute(rows_stmt)).all()
    items = [
        {
            "id": str(r.id),
            "email": r.email,
            "plan": r.plan,
            "credit_balance": int(r.credit_balance),
            "starter_redeem_completed": bool(r.starter_redeem_completed),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_seen_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# GET /internal/admin/payments
# ---------------------------------------------------------------------------

@router.get("/payments")
async def admin_list_payments(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Paginated list of Razorpay payments (newest first), joined to users.

    Rows are only inserted into `razorpay_payments` after the signed payment
    is verified and captured server-side, so every row here is effectively
    `status="captured"`. The field is included for parity with the admin UI
    contract (which anticipates multiple providers / statuses in future).
    """
    _require_internal_api_key(request)
    db = _require_db(session)
    page, page_size = _clamp_pagination(page, page_size)

    total = int(
        (
            await db.execute(select(func.count()).select_from(RazorpayPayment))
        ).scalar()
        or 0
    )

    rows_stmt = (
        select(
            RazorpayPayment.razorpay_payment_id,
            RazorpayPayment.order_id,
            RazorpayPayment.amount_paise,
            RazorpayPayment.created_at,
            User.email,
        )
        .join(User, User.id == RazorpayPayment.user_id)
        .order_by(RazorpayPayment.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(rows_stmt)).all()
    items = [
        {
            "id": r.razorpay_payment_id,
            "order_id": r.order_id,
            "user_email": r.email,
            "provider": "razorpay",
            "status": "captured",
            "amount_paise": int(r.amount_paise),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# Credit codes (catalog + create + deactivate)
# ---------------------------------------------------------------------------

# Visually unambiguous alphabet: no 0/O, no 1/I/L. Easy to read aloud.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_BLOCK_LEN = 4
_CODE_BLOCK_COUNT = 2  # → 8-char body, ~30^8 ≈ 6.5e11 combinations
_CAMPAIGN_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _generate_code(campaign: str | None) -> str:
    body = "-".join(
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_BLOCK_LEN))
        for _ in range(_CODE_BLOCK_COUNT)
    )
    if campaign:
        return f"{campaign.upper()}-{body}"
    return body


class CreateCodesBody(BaseModel):
    credits_each: int = Field(..., gt=0, le=1_000_000)
    count: int = Field(1, ge=1, le=500)
    max_redemptions_per_code: int = Field(1, ge=0, le=1_000_000)
    expires_at: str | None = Field(default=None, max_length=64)
    campaign: str | None = Field(default=None, max_length=32)

    @field_validator("campaign")
    @classmethod
    def _validate_campaign(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not _CAMPAIGN_RE.match(v):
            raise ValueError(
                "campaign must be 1-32 chars of A-Z/a-z/0-9/_/-"
            )
        return v

    @field_validator("expires_at")
    @classmethod
    def _validate_expires_at(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        try:
            if len(v) == 10:
                datetime.fromisoformat(v + "T00:00:00+00:00")
            else:
                datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError("expires_at must be ISO 8601 (e.g. 2026-12-31)") from e
        return v


def _parse_expires_at(s: str | None) -> datetime | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    if len(s) == 10:
        return datetime.fromisoformat(s + "T00:00:00+00:00")
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@router.post("/codes", status_code=201)
async def admin_create_codes(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    body: CreateCodesBody,
) -> dict[str, Any]:
    """Generate one or more credit codes.

    Each generated code is a single row in ``credit_codes`` with the same
    `credits_each`, `max_redemptions`, `expires_at`, and `campaign`. The
    plaintext codes are returned ONCE in the response — they are also
    visible later via ``GET /codes`` for audit, but operators should treat
    this response as the canonical "show to user now" event.
    """
    _require_internal_api_key(request)
    db = _require_db(session)

    expires_at = _parse_expires_at(body.expires_at)

    created: list[str] = []
    for _ in range(body.count):
        last_err: Exception | None = None
        for attempt in range(5):
            code = _generate_code(body.campaign)
            normalized = normalize_redeem_code(code)
            row = CreditCode(
                code=code,
                code_normalized=normalized,
                credits_each=int(body.credits_each),
                max_redemptions=int(body.max_redemptions_per_code),
                redeemed_count=0,
                expires_at=expires_at,
                campaign=body.campaign,
                active=True,
                created_by="admin",
            )
            try:
                async with db.begin_nested():
                    db.add(row)
                    await db.flush()
                created.append(code)
                break
            except IntegrityError as e:
                last_err = e
                logger.warning(
                    "credit code collision on attempt %d (will retry)", attempt + 1
                )
                continue
        else:  # pragma: no cover - alphabet keeps this unreachable
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Could not generate a unique code after 5 attempts.",
            ) from last_err

    await db.commit()
    return {
        "codes": created,
        "count": len(created),
        "credits_each": int(body.credits_each),
        "max_redemptions_per_code": int(body.max_redemptions_per_code),
        "campaign": body.campaign,
        "expires_at": body.expires_at,
    }


@router.get("/codes")
async def admin_list_codes(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    active_only: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """List admin-issued credit codes, newest first."""
    _require_internal_api_key(request)
    db = _require_db(session)
    page, page_size = _clamp_pagination(page, page_size)

    base_filters = []
    if active_only:
        base_filters.append(CreditCode.active.is_(True))

    total_stmt = select(func.count()).select_from(CreditCode)
    if base_filters:
        total_stmt = total_stmt.where(*base_filters)
    total = int((await db.execute(total_stmt)).scalar() or 0)

    rows_stmt = (
        select(CreditCode)
        .order_by(CreditCode.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if base_filters:
        rows_stmt = rows_stmt.where(*base_filters)
    rows = (await db.execute(rows_stmt)).scalars().all()
    items = [
        {
            "code": r.code,
            "credits_each": int(r.credits_each),
            "max_redemptions": int(r.max_redemptions),
            "redeemed_count": int(r.redeemed_count),
            "active": bool(r.active),
            "campaign": r.campaign,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/codes/{code}/deactivate")
async def admin_deactivate_code(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    code: Annotated[str, Path(min_length=1, max_length=64)],
) -> dict[str, Any]:
    """Soft-deactivate a code so future redeem attempts are rejected.

    Existing redemptions are preserved. Idempotent: deactivating an
    already-inactive code returns 200 with `was_active=false`.
    """
    _require_internal_api_key(request)
    db = _require_db(session)
    normalized = normalize_redeem_code(code)
    row = (
        await db.execute(
            select(CreditCode).where(CreditCode.code_normalized == normalized)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Credit code not found.")
    was_active = bool(row.active)
    row.active = False
    await db.commit()
    return {
        "code": row.code,
        "active": False,
        "was_active": was_active,
        "redeemed_count": int(row.redeemed_count),
    }


# ---------------------------------------------------------------------------
# GET /internal/admin/activity  (powers the Activity log page)
# ---------------------------------------------------------------------------

# Reasons emitted by the existing app code paths. Kept as a frozen catalogue
# so the admin UI can show a stable filter dropdown and so we can classify
# rows into grant / spend / refund without parsing strings client-side.
#
# When new reasons are added in `credit_service` / `main` / `credit_holds`,
# add them here too — unknown reasons still render fine, they just default
# to ``kind="other"`` and a humanised label.
_REASON_KIND: dict[str, str] = {
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
    "tts_generate": "spend",
}

_REASON_LABEL: dict[str, str] = {
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
    "tts_generate": "TTS generated",
}


def _classify(reason: str, delta: int) -> tuple[str, str]:
    kind = _REASON_KIND.get(reason)
    if kind is None:
        kind = "grant" if delta >= 0 else "spend"
    label = _REASON_LABEL.get(reason, reason.replace("_", " ").title())
    return kind, label


@router.get("/activity")
async def admin_activity_feed(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    q: Annotated[str | None, Query(max_length=320)] = None,
    reason: Annotated[str | None, Query(max_length=64)] = None,
    kind: Annotated[str | None, Query(pattern="^(grant|spend|refund|other)$")] = None,
) -> dict[str, Any]:
    """Paginated activity feed sourced from `credit_ledger` + `users`.

    This is intentionally read-only and uses the existing ledger table —
    every monetary or usage event in the app already lands there, so no
    new emit code (and no risk to existing flows) is needed to populate
    it. The ledger is indexed on `user_id`; this endpoint orders by
    ``created_at DESC`` with offset pagination, which stays cheap up to
    a few million rows.

    Filters:
      * ``q``      — case-insensitive substring match on user email.
      * ``reason`` — exact match against `credit_ledger.reason`.
      * ``kind``   — one of ``grant`` / ``spend`` / ``refund`` / ``other``,
                     translated to a set of concrete reasons server-side.
    """
    _require_internal_api_key(request)
    db = _require_db(session)
    page, page_size = _clamp_pagination(page, page_size)

    base_filters = []
    q_clean = (q or "").strip()
    if q_clean:
        like = f"%{q_clean.lower()}%"
        base_filters.append(func.lower(User.email).like(like))
    if reason:
        base_filters.append(CreditLedger.reason == reason.strip())
    if kind:
        wanted = {r for r, k in _REASON_KIND.items() if k == kind}
        if kind == "other":
            known = set(_REASON_KIND.keys())
            base_filters.append(~CreditLedger.reason.in_(known))
        elif wanted:
            base_filters.append(CreditLedger.reason.in_(wanted))
        else:
            # No reasons map to this kind yet — return an empty page.
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "reasons": sorted(_REASON_LABEL.keys()),
            }

    total_stmt = (
        select(func.count())
        .select_from(CreditLedger)
        .join(User, User.id == CreditLedger.user_id)
    )
    if base_filters:
        total_stmt = total_stmt.where(*base_filters)
    total = int((await db.execute(total_stmt)).scalar() or 0)

    rows_stmt = (
        select(
            CreditLedger.id,
            CreditLedger.user_id,
            CreditLedger.delta,
            CreditLedger.balance_after,
            CreditLedger.reason,
            CreditLedger.meta,
            CreditLedger.created_at,
            User.email,
        )
        .join(User, User.id == CreditLedger.user_id)
        .order_by(CreditLedger.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if base_filters:
        rows_stmt = rows_stmt.where(*base_filters)

    rows = (await db.execute(rows_stmt)).all()
    items: list[dict[str, Any]] = []
    for r in rows:
        k, label = _classify(r.reason, int(r.delta))
        items.append(
            {
                "id": str(r.id),
                "user_id": str(r.user_id),
                "user_email": r.email,
                "delta": int(r.delta),
                "balance_after": int(r.balance_after),
                "reason": r.reason,
                "kind": k,
                "label": label,
                "meta": r.meta,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "reasons": sorted(_REASON_LABEL.keys()),
    }


# ---------------------------------------------------------------------------
# Content templates (upload + manage; consumed by user dashboard via
# /api/templates/feed which lives in its own public router).
# ---------------------------------------------------------------------------

# S3 prefix for admin-uploaded templates. Intentionally independent from
# settings.s3_prefix (jobs/) so templates live at a well-known, bucket-level
# location operators can reason about from the S3 console.
_TEMPLATES_S3_PREFIX = "templates/"

# Hard upload caps to keep memory usage bounded on both EC2s.
_MAX_IMAGE_BYTES = 10 * 1024 * 1024   # 10 MB
_MAX_VIDEO_BYTES = 50 * 1024 * 1024   # 50 MB

_ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
_ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
}

# Admin preview URLs expire in an hour — page loads refresh the cache anyway.
_ADMIN_PREVIEW_TTL = 3600


def _templates_s3_key(template_id: uuid.UUID, ext: str) -> str:
    # `templates/<id>.<ext>` — flat layout, one object per template row.
    ext = (ext or "").lstrip(".").lower()[:8] or "bin"
    return f"{_TEMPLATES_S3_PREFIX}{template_id}.{ext}"


def _ext_from_content_type(content_type: str) -> str:
    m = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
        "video/mp4": "mp4",
        "video/webm": "webm",
        "video/quicktime": "mov",
    }
    return m.get(content_type.lower(), "bin")


def _normalise_tags(raw: str | None) -> str | None:
    if not raw:
        return None
    parts = [t.strip() for t in raw.split(",")]
    parts = [t for t in parts if t]
    if not parts:
        return None
    return ",".join(parts)[:256]


@router.post("/templates/upload", status_code=201)
async def admin_upload_template(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    kind: Annotated[str, Form(pattern="^(image|video)$")],
    description: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form(max_length=64)] = None,
    language: Annotated[str | None, Form(max_length=8)] = None,
    tags: Annotated[str | None, Form(max_length=256)] = None,
    published: Annotated[bool, Form()] = False,
    sort_order: Annotated[int, Form(ge=-1000, le=1000)] = 0,
) -> dict[str, Any]:
    """Upload a template asset to S3 and record its metadata.

    The file is streamed through this process into S3 (bucket reused from
    the existing app, prefix ``templates/``). IAM is provided by the FastAPI
    EC2 instance profile — no new credentials are introduced.
    """
    _require_internal_api_key(request)
    db = _require_db(session)

    settings = _load_settings()
    bucket = (settings.s3_bucket or "").strip()
    if not bucket:
        raise HTTPException(
            status_code=503, detail="S3 is not configured on this backend."
        )

    ct_raw = (file.content_type or "").split(";")[0].strip().lower()
    allowed = _ALLOWED_IMAGE_TYPES if kind == "image" else _ALLOWED_VIDEO_TYPES
    if ct_raw not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content-type '{ct_raw}' for kind={kind}.",
        )
    max_bytes = _MAX_IMAGE_BYTES if kind == "image" else _MAX_VIDEO_BYTES

    payload = await file.read(max_bytes + 1)
    if len(payload) == 0:
        raise HTTPException(status_code=400, detail="Empty upload.")
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {max_bytes // (1024 * 1024)} MB limit.",
        )

    template_id = uuid.uuid4()
    s3_key = _templates_s3_key(template_id, _ext_from_content_type(ct_raw))

    # Lazy import so the templates admin path is independent of the /generate
    # critical path; if boto3 isn't importable we fail cleanly here without
    # affecting anything else.
    from app.services.s3_storage import s3_client  # noqa: PLC0415

    try:
        client = s3_client(settings)
        client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=payload,
            ContentType=ct_raw,
            CacheControl="public, max-age=86400",
        )
    except Exception as e:  # pragma: no cover - surface S3 errors cleanly
        logger.exception("Template S3 upload failed (key=%s)", s3_key)
        raise HTTPException(
            status_code=502, detail=f"S3 upload failed: {e}"
        ) from e

    row = ContentTemplate(
        id=template_id,
        kind=kind,
        title=title.strip(),
        description=(description or "").strip() or None,
        category=(category or "").strip() or None,
        language=(language or "").strip().lower() or None,
        s3_key=s3_key,
        content_type=ct_raw,
        size_bytes=len(payload),
        tags=_normalise_tags(tags),
        published=bool(published),
        sort_order=int(sort_order),
        created_by="admin",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    return _template_to_dict(row, settings=settings, include_preview=True)


def _template_to_dict(
    row: ContentTemplate,
    *,
    settings: Settings,
    include_preview: bool,
) -> dict[str, Any]:
    preview_url: str | None = None
    if include_preview:
        try:
            from app.services.s3_storage import safe_presign_get  # noqa: PLC0415

            preview_url = safe_presign_get(settings, row.s3_key)
        except Exception:
            logger.exception("presign failed for %s", row.s3_key)
            preview_url = None
    return {
        "id": str(row.id),
        "kind": row.kind,
        "title": row.title,
        "description": row.description,
        "category": row.category,
        "language": row.language,
        "s3_key": row.s3_key,
        "content_type": row.content_type,
        "size_bytes": int(row.size_bytes),
        "width": row.width,
        "height": row.height,
        "duration_seconds": row.duration_seconds,
        "tags": row.tags,
        "published": bool(row.published),
        "sort_order": int(row.sort_order),
        "preview_url": preview_url,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/templates")
async def admin_list_templates(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 30,
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: Annotated[str | None, Query(pattern="^(image|video)$")] = None,
    published: Annotated[str | None, Query(pattern="^(true|false)$")] = None,
) -> dict[str, Any]:
    """List templates with fresh preview URLs for the admin gallery."""
    _require_internal_api_key(request)
    db = _require_db(session)
    page, page_size = _clamp_pagination(page, page_size)
    settings = _load_settings()

    filters = []
    q_clean = (q or "").strip().lower()
    if q_clean:
        like = f"%{q_clean}%"
        filters.append(
            or_(
                func.lower(ContentTemplate.title).like(like),
                func.lower(func.coalesce(ContentTemplate.category, "")).like(like),
                func.lower(func.coalesce(ContentTemplate.tags, "")).like(like),
            )
        )
    if kind:
        filters.append(ContentTemplate.kind == kind)
    if published is not None:
        filters.append(ContentTemplate.published.is_(published == "true"))

    total_stmt = select(func.count()).select_from(ContentTemplate)
    if filters:
        total_stmt = total_stmt.where(*filters)
    total = int((await db.execute(total_stmt)).scalar() or 0)

    rows_stmt = (
        select(ContentTemplate)
        .order_by(
            ContentTemplate.sort_order.asc(),
            ContentTemplate.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if filters:
        rows_stmt = rows_stmt.where(*filters)
    rows = (await db.execute(rows_stmt)).scalars().all()

    return {
        "items": [
            _template_to_dict(r, settings=settings, include_preview=True)
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


class UpdateTemplateBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None)
    category: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=8)
    tags: str | None = Field(default=None, max_length=256)
    published: bool | None = None
    sort_order: int | None = Field(default=None, ge=-1000, le=1000)


@router.patch("/templates/{template_id}")
async def admin_update_template(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    body: UpdateTemplateBody,
    template_id: Annotated[uuid.UUID, Path()],
) -> dict[str, Any]:
    """Partial edit of a template's metadata."""
    _require_internal_api_key(request)
    db = _require_db(session)
    row = (
        await db.execute(
            select(ContentTemplate).where(ContentTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    if body.title is not None:
        row.title = body.title.strip() or row.title
    if body.description is not None:
        row.description = body.description.strip() or None
    if body.category is not None:
        row.category = body.category.strip() or None
    if body.language is not None:
        row.language = body.language.strip().lower() or None
    if body.tags is not None:
        row.tags = _normalise_tags(body.tags)
    if body.published is not None:
        row.published = bool(body.published)
    if body.sort_order is not None:
        row.sort_order = int(body.sort_order)

    await db.commit()
    await db.refresh(row)
    return _template_to_dict(row, settings=_load_settings(), include_preview=True)


@router.post("/templates/{template_id}/publish")
async def admin_toggle_publish(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    template_id: Annotated[uuid.UUID, Path()],
    publish: Annotated[bool, Query()] = True,
) -> dict[str, Any]:
    _require_internal_api_key(request)
    db = _require_db(session)
    row = (
        await db.execute(
            select(ContentTemplate).where(ContentTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    row.published = bool(publish)
    await db.commit()
    await db.refresh(row)
    return {
        "id": str(row.id),
        "published": bool(row.published),
    }


@router.delete("/templates/{template_id}")
async def admin_delete_template(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    template_id: Annotated[uuid.UUID, Path()],
) -> dict[str, Any]:
    """Remove the row and the S3 object. S3 delete errors don't block the row delete."""
    _require_internal_api_key(request)
    db = _require_db(session)
    row = (
        await db.execute(
            select(ContentTemplate).where(ContentTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found.")

    s3_key = row.s3_key
    settings = _load_settings()
    bucket = (settings.s3_bucket or "").strip()

    await db.delete(row)
    await db.commit()

    # Best-effort S3 cleanup after the DB commit so a transient S3 failure
    # doesn't leave a dangling row.
    try:
        from app.services.s3_storage import s3_client  # noqa: PLC0415

        client = s3_client(settings)
        client.delete_object(Bucket=bucket, Key=s3_key)
    except Exception:
        logger.exception("Template S3 delete failed (key=%s)", s3_key)

    return {"id": str(template_id), "deleted": True, "s3_key": s3_key}
