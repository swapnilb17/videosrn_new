"""CRUD helpers for the per-user media library (MediaItem table)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediaItem


async def media_insert(
    session: AsyncSession,
    *,
    owner_email: str,
    media_type: str,
    title: str,
    media_url: str,
    source_service: str,
    thumbnail_url: str | None = None,
    extra: dict[str, Any] | None = None,
) -> uuid.UUID:
    item_id = uuid.uuid4()
    session.add(
        MediaItem(
            id=item_id,
            owner_email=owner_email,
            media_type=media_type,
            title=title,
            media_url=media_url,
            thumbnail_url=thumbnail_url,
            source_service=source_service,
            extra=extra,
        )
    )
    await session.commit()
    return item_id


async def media_list_by_owner(
    session: AsyncSession,
    owner_email: str,
    *,
    media_type: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return media items for a user, newest first. Strict tenant isolation."""
    stmt = (
        select(MediaItem)
        .where(MediaItem.owner_email == owner_email)
    )
    if media_type:
        stmt = stmt.where(MediaItem.media_type == media_type)
    stmt = stmt.order_by(MediaItem.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": str(row.id),
            "media_type": row.media_type,
            "title": row.title,
            "media_url": row.media_url,
            "thumbnail_url": row.thumbnail_url,
            "source_service": row.source_service,
            "extra": row.extra,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
