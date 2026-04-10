"""Resolve User row for credit operations from OAuth session or form fields."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.credit_service import get_or_create_user
from app.models import User


def _pick_email(google_user: dict | None, user_email: str | None) -> str:
    if google_user and isinstance(google_user.get("email"), str):
        e = google_user["email"].strip()
        if e:
            return e
    return (user_email or "").strip()


def _pick_sub(google_user: dict | None, user_sub: str | None) -> str | None:
    if google_user and isinstance(google_user.get("sub"), str):
        s = google_user["sub"].strip()
        if s:
            return s
    s2 = (user_sub or "").strip()
    return s2 or None


async def resolve_user_for_credits(
    session: AsyncSession | None,
    *,
    google_user: dict | None,
    user_email: str | None = None,
    user_sub: str | None = None,
) -> User | None:
    """Return User or None if identity cannot be resolved (caller may 401)."""
    if session is None:
        return None
    email = _pick_email(google_user, user_email)
    if not email or "@" not in email:
        return None
    sub = _pick_sub(google_user, user_sub)
    return await get_or_create_user(session, email=email, google_sub=sub)
