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
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import get_db_session
from app.models import RazorpayPayment, User

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
