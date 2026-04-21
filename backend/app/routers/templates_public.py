"""Public, unauthenticated templates feed for the user dashboard.

This router is deliberately separate from the admin router so it can be
reviewed / rate-limited / disabled independently. It only returns rows
flagged ``published = true`` and generates short-lived presigned S3 GET
URLs for playback.

The endpoint is cheap (small joinless query + presigned URL signing) and
the user dashboard caches responses for 60 seconds, mirroring the BFF
cache strategy used by the admin app.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db_session
from app.models import ContentTemplate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("/feed")
async def templates_feed(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    kind: Annotated[str | None, Query(pattern="^(image|video)$")] = None,
    category: Annotated[str | None, Query(max_length=64)] = None,
    language: Annotated[str | None, Query(max_length=8)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 60,
) -> dict[str, Any]:
    """Return the published template gallery for end users.

    Response shape is intentionally minimal — only what the dashboard needs
    to render cards + play previews. No admin-only fields (created_by,
    sort_order internals) are exposed.
    """
    if session is None:
        return {"items": []}

    bucket = (settings.s3_bucket or "").strip()
    if not bucket:
        return {"items": []}

    stmt = (
        select(ContentTemplate)
        .where(ContentTemplate.published.is_(True))
        .order_by(
            ContentTemplate.sort_order.asc(),
            ContentTemplate.created_at.desc(),
        )
        .limit(limit)
    )
    if kind:
        stmt = stmt.where(ContentTemplate.kind == kind)
    if category:
        stmt = stmt.where(ContentTemplate.category == category.strip())
    if language:
        stmt = stmt.where(ContentTemplate.language == language.strip().lower())

    rows = (await session.execute(stmt)).scalars().all()

    # Import lazily so the feed endpoint doesn't couple to S3 at import time.
    from app.services.s3_storage import safe_presign_get  # noqa: PLC0415

    items: list[dict[str, Any]] = []
    for r in rows:
        try:
            url = safe_presign_get(settings, r.s3_key)
        except Exception:
            logger.exception("templates feed: presign failed key=%s", r.s3_key)
            continue
        thumb_url: str | None = None
        if r.thumbnail_s3_key:
            try:
                thumb_url = safe_presign_get(settings, r.thumbnail_s3_key)
            except Exception:
                logger.exception(
                    "templates feed: thumb presign failed key=%s", r.thumbnail_s3_key
                )
        items.append(
            {
                "id": str(r.id),
                "kind": r.kind,
                "title": r.title,
                "description": r.description,
                "category": r.category,
                "language": r.language,
                "content_type": r.content_type,
                "width": r.width,
                "height": r.height,
                "duration_seconds": r.duration_seconds,
                "tags": [t for t in (r.tags or "").split(",") if t],
                "url": url,
                "thumbnail_url": thumb_url,
            }
        )
    return {"items": items}
