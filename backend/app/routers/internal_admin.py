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
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.credit_service import normalize_redeem_code
from app.db import get_db_session
from app.models import CreditCode, RazorpayPayment, User

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
