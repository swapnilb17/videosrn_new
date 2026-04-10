"""In-memory credit holds for async jobs (refund on pipeline failure)."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.credit_service import add_credits
from app.models import User

logger = logging.getLogger(__name__)

_holds: dict[str, tuple[uuid.UUID, int]] = {}


def register_credit_hold(job_id: str, user_id: uuid.UUID, amount: int) -> None:
    if amount > 0:
        _holds[job_id] = (user_id, amount)


async def release_credit_hold(
    session_factory: async_sessionmaker[AsyncSession] | None,
    job_id: str,
    *,
    success: bool,
) -> None:
    """On failure, refund held credits. On success, drop hold without refund."""
    entry = _holds.pop(job_id, None)
    if entry is None:
        return
    user_id, amount = entry
    if success or amount <= 0:
        return
    if session_factory is None:
        logger.warning("credit refund skipped: no session factory for job %s", job_id)
        return
    async with session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            logger.warning("credit refund: user %s missing for job %s", user_id, job_id)
            return
        await add_credits(
            session,
            user,
            amount,
            reason="refund_failed_job",
            meta={"job_id": job_id},
        )
        await session.commit()
