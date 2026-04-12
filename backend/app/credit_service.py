"""Credit balance, ledger, pricing, and starter redeem (Phase A/B)."""

from __future__ import annotations

import logging
import math
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import CreditLedger, CreditPromoRedemption, User

logger = logging.getLogger(__name__)

# --- Pricing (1 credit = 1 INR) ---
SIGNUP_CREDITS = 50
# Standard (Topic → Video): per target second, rounded up to whole credits
STANDARD_VIDEO_CREDITS_PER_SECOND = 0.75
STANDARD_VIDEO_ENHANCE_CREDITS_PER_SECOND = 1.75
# Starter redeem tops balance up to this (Free signup stays SIGNUP_CREDITS once)
STARTER_CREDITS_TARGET = 500
IMAGE_CREDITS_PER_IMAGE = 5
TTS_CREDITS_PER_2K_CHARS = 2
VEO_LITE_CREDITS_PER_SECOND_720 = 15
VEO_LITE_CREDITS_PER_SECOND_1080 = 25

STARTER_REDEEM_CODE = "enably499"

# Shared credit promo codes — each string may be redeemed once globally (first account wins).
PROMO_CREDIT_CODES: dict[str, int] = {
    "enably2000": 2000,
    "enably1000": 1000,
    "enably1500": 1500,
    "enably700": 700,
}

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


def standard_video_credit_cost(target_seconds: int, *, enhance_motion: bool) -> int:
    """Credits for /generate standard pipeline: ceil(duration × rate), minimum 1."""
    ts = max(1, int(target_seconds))
    rate = (
        STANDARD_VIDEO_ENHANCE_CREDITS_PER_SECOND
        if enhance_motion
        else STANDARD_VIDEO_CREDITS_PER_SECOND
    )
    return max(1, math.ceil(ts * rate))


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


async def _has_starter_redeem_grant_ledger(session: AsyncSession, user_id: uuid.UUID) -> bool:
    r = await session.execute(
        select(CreditLedger.id).where(
            CreditLedger.user_id == user_id,
            CreditLedger.reason == "starter_redeem_grant",
        ).limit(1)
    )
    return r.scalar_one_or_none() is not None


async def ensure_starter_legacy_topup(session: AsyncSession, user: User) -> None:
    """Top up to STARTER_CREDITS_TARGET if Starter was redeemed before grant ledger existed.

    New redeems record ``starter_redeem_grant`` in the ledger. Older accounts have
    ``starter_redeem_completed`` but no such row and never received the 500 top-up.
    If a ``starter_redeem_grant`` row exists, we assume the quota was already applied
    (user may have spent down — do not top up again).
    """
    if user.plan != PLAN_STARTER or not user.starter_redeem_completed:
        return
    if await _has_starter_redeem_grant_ledger(session, user.id):
        return
    need = max(0, STARTER_CREDITS_TARGET - int(user.credit_balance))
    if need <= 0:
        return
    logger.info(
        "Starter legacy top-up for %s: +%s credits (toward %s, no prior starter_redeem_grant)",
        user.email,
        need,
        STARTER_CREDITS_TARGET,
    )
    await add_credits(
        session,
        user,
        need,
        reason="starter_redeem_grant",
        meta={"legacy_backfill": True, "target_balance": STARTER_CREDITS_TARGET},
    )


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
    await ensure_starter_legacy_topup(session, user)
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


def normalize_redeem_code(raw: str) -> str:
    return re.sub(r"\s+", "", (raw or "").strip().lower())


async def _promo_code_already_redeemed(session: AsyncSession, code_normalized: str) -> bool:
    r = await session.execute(
        select(CreditPromoRedemption.code_normalized).where(
            CreditPromoRedemption.code_normalized == code_normalized
        )
    )
    return r.scalar_one_or_none() is not None


async def redeem_promo_credit_code(
    session: AsyncSession,
    user: User,
    code_normalized: str,
    credits: int,
) -> None:
    """Grant credits + Starter plan; code row is unique so only one redeem succeeds worldwide."""
    try:
        async with session.begin_nested():
            session.add(
                CreditPromoRedemption(
                    code_normalized=code_normalized,
                    redeemed_by_user_id=user.id,
                    credits_amount=int(credits),
                )
            )
            await session.flush()
    except IntegrityError as e:
        raise ValueError("This credit code has already been redeemed") from e
    await add_credits(
        session,
        user,
        int(credits),
        reason="promo_code_grant",
        meta={"code": code_normalized},
    )
    user.plan = PLAN_STARTER
    await session.flush()


async def _redeem_starter_normalized(session: AsyncSession, user: User) -> None:
    if user.starter_redeem_completed:
        raise ValueError("Starter code already redeemed on this account")
    user.starter_redeem_completed = True
    user.plan = PLAN_STARTER
    need = max(0, STARTER_CREDITS_TARGET - int(user.credit_balance))
    if need > 0:
        await add_credits(
            session,
            user,
            need,
            reason="starter_redeem_grant",
            meta={"target_balance": STARTER_CREDITS_TARGET},
        )
    await session.flush()


async def redeem_code(session: AsyncSession, user: User, code: str) -> None:
    """Starter invite (enably499) or single-use credit promo codes (Enably2000, …)."""
    raw = (code or "").strip()
    if not raw:
        raise ValueError("code is required")
    normalized = normalize_redeem_code(raw)
    if normalized in PROMO_CREDIT_CODES:
        await redeem_promo_credit_code(
            session, user, normalized, PROMO_CREDIT_CODES[normalized]
        )
        return
    if normalized == STARTER_REDEEM_CODE:
        await _redeem_starter_normalized(session, user)
        return
    raise ValueError("Invalid or expired code")


async def redeem_starter_code(
    session: AsyncSession,
    user: User,
    code: str,
) -> None:
    """Backward-compatible name; delegates to :func:`redeem_code`."""
    await redeem_code(session, user, code)


async def check_credit_code(
    session: AsyncSession,
    user: User,
    code: str,
) -> dict[str, Any]:
    """Validate a code without mutating balances (for “Check code” in the UI)."""
    raw = (code or "").strip()
    if not raw:
        return {"ok": True, "valid": False, "reason": "empty", "message": "Enter a code"}
    normalized = normalize_redeem_code(raw)
    if normalized in PROMO_CREDIT_CODES:
        amount = PROMO_CREDIT_CODES[normalized]
        taken = await _promo_code_already_redeemed(session, normalized)
        if taken:
            return {
                "ok": True,
                "valid": False,
                "kind": "promo",
                "credits": amount,
                "already_used_globally": True,
                "message": "This code was already used (each code works once).",
            }
        return {
            "ok": True,
            "valid": True,
            "kind": "promo",
            "credits": amount,
            "already_used_globally": False,
            "message": f"Valid — redeems {amount} credits and enables Starter (Veo) while you have balance.",
        }
    if normalized == STARTER_REDEEM_CODE:
        if user.starter_redeem_completed:
            return {
                "ok": True,
                "valid": False,
                "kind": "starter",
                "already_used_on_account": True,
                "message": "Starter code already redeemed on this account.",
            }
        need = max(0, STARTER_CREDITS_TARGET - int(user.credit_balance))
        return {
            "ok": True,
            "valid": True,
            "kind": "starter",
            "credits_top_up": need,
            "target_balance": STARTER_CREDITS_TARGET,
            "already_used_on_account": False,
            "message": (
                f"Valid — unlocks Starter; adds up to {STARTER_CREDITS_TARGET} credits "
                f"({need} credits will be added with your current balance)."
            ),
        }
    return {
        "ok": True,
        "valid": False,
        "kind": "unknown",
        "message": "Unknown or expired code.",
    }


def can_use_premium_models(user: User) -> bool:
    return user.plan == PLAN_STARTER
