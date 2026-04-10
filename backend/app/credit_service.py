"""Credit balance, ledger, pricing, and starter redeem (Phase A/B)."""

from __future__ import annotations

import logging
import math
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import CreditLedger, User

logger = logging.getLogger(__name__)

# --- Pricing (1 credit = 1 INR) ---
SIGNUP_CREDITS = 50
STANDARD_VIDEO_CREDITS_PER_SECOND = 5
IMAGE_CREDITS_PER_IMAGE = 5
TTS_CREDITS_PER_2K_CHARS = 2
VEO_LITE_CREDITS_PER_SECOND_720 = 15
VEO_LITE_CREDITS_PER_SECOND_1080 = 25

STARTER_REDEEM_CODE = "enably499"

PLAN_FREE = "free"
PLAN_STARTER = "starter"


def normalize_email(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    return s


def tts_credits_for_chars(char_count: int) -> int:
    if char_count <= 0:
        return 0
    blocks = max(1, math.ceil(char_count / 2000))
    return blocks * TTS_CREDITS_PER_2K_CHARS


def veo_credits_for_seconds(duration_seconds: int, *, is_1080p: bool) -> int:
    """Bill output seconds (Veo snaps to 4/6/8 in API; we bill requested duration after snap)."""
    ds = max(1, int(duration_seconds))
    rate = VEO_LITE_CREDITS_PER_SECOND_1080 if is_1080p else VEO_LITE_CREDITS_PER_SECOND_720
    return ds * rate


def _veo_is_1080p(width: int, height: int) -> bool:
    return max(width, height) >= 1080


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    em = normalize_email(email)
    if not em:
        return None
    r = await session.execute(select(User).where(User.email == em))
    return r.scalar_one_or_none()


async def get_user_by_sub(session: AsyncSession, sub: str) -> User | None:
    s = (sub or "").strip()
    if not s:
        return None
    r = await session.execute(select(User).where(User.google_sub == s))
    return r.scalar_one_or_none()


async def _has_signup_grant_ledger(session: AsyncSession, user_id: uuid.UUID) -> bool:
    r = await session.execute(
        select(CreditLedger.id).where(
            CreditLedger.user_id == user_id,
            CreditLedger.reason == "signup_grant",
        ).limit(1)
    )
    return r.scalar_one_or_none() is not None


async def ensure_signup_grant_integrity(session: AsyncSession, user: User) -> None:
    """Apply one-time signup credits if there is no signup_grant ledger row.

    Repairs inconsistent rows where ``signup_grant_completed`` was set without a ledger
    (e.g. failed transaction or manual DB edits), which otherwise show balance 0 forever.
    """
    if await _has_signup_grant_ledger(session, user.id):
        return
    if user.signup_grant_completed:
        logger.warning(
            "Repairing signup grant: user %s has signup_grant_completed without ledger; adding %s credits",
            user.email,
            SIGNUP_CREDITS,
        )
        user.signup_grant_completed = False
    await apply_signup_grant(session, user)


async def get_or_create_user(
    session: AsyncSession,
    *,
    email: str,
    google_sub: str | None = None,
) -> User:
    """Create user with one-time signup grant; link google_sub when missing."""
    em = normalize_email(email)
    if not em or "@" not in em:
        raise ValueError("valid email is required")

    user = await get_user_by_email(session, em)
    if user is None and google_sub:
        user = await get_user_by_sub(session, google_sub.strip())

    if user is None:
        user = User(
            email=em,
            google_sub=google_sub.strip() if google_sub else None,
            credit_balance=0,
            plan=PLAN_FREE,
            signup_grant_completed=False,
            starter_redeem_completed=False,
        )
        session.add(user)
        await session.flush()
    elif google_sub and not user.google_sub:
        user.google_sub = google_sub.strip()

    await ensure_signup_grant_integrity(session, user)
    await session.flush()
    return user


async def apply_signup_grant(session: AsyncSession, user: User) -> None:
    if user.signup_grant_completed:
        return
    await add_credits(
        session,
        user,
        SIGNUP_CREDITS,
        reason="signup_grant",
        meta={"source": "signup"},
    )
    user.signup_grant_completed = True


async def add_credits(
    session: AsyncSession,
    user: User,
    amount: int,
    *,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> None:
    if amount == 0:
        return
    user.credit_balance = int(user.credit_balance) + int(amount)
    session.add(
        CreditLedger(
            id=uuid.uuid4(),
            user_id=user.id,
            delta=int(amount),
            balance_after=user.credit_balance,
            reason=reason,
            meta=meta,
        )
    )


async def deduct_credits(
    session: AsyncSession,
    user: User,
    amount: int,
    *,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> None:
    if amount <= 0:
        return
    bal = int(user.credit_balance)
    if bal < amount:
        raise InsufficientCreditsError(bal, amount)
    user.credit_balance = bal - amount
    session.add(
        CreditLedger(
            id=uuid.uuid4(),
            user_id=user.id,
            delta=-int(amount),
            balance_after=user.credit_balance,
            reason=reason,
            meta=meta,
        )
    )


class InsufficientCreditsError(Exception):
    def __init__(self, balance: int, required: int) -> None:
        self.balance = balance
        self.required = required
        super().__init__(f"Insufficient credits: have {balance}, need {required}")


class PremiumRequiredError(Exception):
    """Veo / premium models need starter plan."""

    pass


async def lock_user_for_update(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    r = await session.execute(
        select(User).where(User.id == user_id).with_for_update()
    )
    return r.scalar_one_or_none()


async def redeem_starter_code(
    session: AsyncSession,
    user: User,
    code: str,
) -> None:
    raw = (code or "").strip()
    if not raw:
        raise ValueError("code is required")
    normalized = re.sub(r"\s+", "", raw.lower())
    if normalized != STARTER_REDEEM_CODE:
        raise ValueError("Invalid or expired code")
    if user.starter_redeem_completed:
        raise ValueError("Starter code already redeemed on this account")
    user.starter_redeem_completed = True
    user.plan = PLAN_STARTER
    await session.flush()


def can_use_premium_models(user: User) -> bool:
    return user.plan == PLAN_STARTER
