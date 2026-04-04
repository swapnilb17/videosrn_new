import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job


async def job_insert_running(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    topic: str,
    language: str,
    branding_logo_applied: bool,
    owner_sub: str | None = None,
) -> None:
    session.add(
        Job(
            id=job_id,
            status="running",
            topic=topic,
            language=language,
            branding_logo_applied=branding_logo_applied,
            owner_sub=owner_sub,
        )
    )
    await session.commit()


async def job_update_script(
    session: AsyncSession,
    job_id: uuid.UUID,
    script: dict[str, Any],
) -> None:
    row = await session.get(Job, job_id)
    if row is None:
        return
    row.script = script
    await session.commit()


async def job_mark_failed(
    session: AsyncSession,
    job_id: uuid.UUID,
    message: str,
) -> None:
    row = await session.get(Job, job_id)
    if row is None:
        return
    row.status = "failed"
    row.error_message = message[:4000]
    await session.commit()


async def job_mark_succeeded(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    tts_provider: str,
    visual_mode: str,
    visual_detail: str | None,
    branding_logo_applied: bool,
    s3_keys: dict[str, str],
) -> None:
    row = await session.get(Job, job_id)
    if row is None:
        return
    row.status = "succeeded"
    row.tts_provider = tts_provider
    row.visual_mode = visual_mode
    row.visual_detail = visual_detail
    row.branding_logo_applied = branding_logo_applied
    row.s3_keys = s3_keys
    row.error_message = None
    await session.commit()


async def job_get_media_asset(
    session: AsyncSession,
    job_id: uuid.UUID,
    filename: str,
) -> tuple[str | None, str | None]:
    """Return (s3 object key, owner_sub) for a succeeded job file, or (None, None)."""
    row = await session.get(Job, job_id)
    if row is None or row.status != "succeeded":
        return None, None
    keys = row.s3_keys or {}
    return keys.get(filename), row.owner_sub
