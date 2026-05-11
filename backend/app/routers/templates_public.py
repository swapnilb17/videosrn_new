"""Public, unauthenticated templates feed for the user dashboard.

This router is deliberately separate from the admin router so it can be
reviewed / rate-limited / disabled independently. It only returns rows
flagged ``published = true`` and generates short-lived presigned S3 GET
URLs for playback.

The endpoint is cheap (small joinless query + presigned URL signing) and
the user dashboard caches responses for 60 seconds, mirroring the BFF
cache strategy used by the admin app.

The companion ``/{template_id}/asset`` endpoint streams the underlying
object bytes directly through the backend so the browser can re-upload
the template as a reference image / start frame for the "Remix" flow —
something the presigned URL can't power because S3 isn't CORS-enabled
for our origin.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db_session
from app.models import ContentTemplate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/templates", tags=["templates"])

_MAX_ASSET_BYTES = 25 * 1024 * 1024  # 25 MB hard cap on the streamed payload.


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


@router.get("/{template_id}/asset")
async def template_asset(
    template_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    variant: Annotated[str, Query(pattern="^(image|thumbnail)$")] = "image",
) -> StreamingResponse:
    """Stream the raw bytes of a published template's asset from S3.

    Powers the dashboard's "Remix" flow: the browser fetches this endpoint
    same-origin to get the bytes into a Blob/File, then re-uploads them as
    a reference image (text-to-image) or start frame (image-to-video).

    ``variant``:
        - ``image`` (default): the main template asset (the image for image
          templates, or the source video for video templates).
        - ``thumbnail``: the still-frame thumbnail stored under
          ``thumbnail_s3_key``. For video templates this is the only usable
          asset for "start from this frame" remixing; for image templates
          we fall back to the main asset if no thumbnail exists.
    """
    if session is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")

    bucket = (settings.s3_bucket or "").strip()
    if not bucket:
        raise HTTPException(status_code=503, detail="S3 is not configured.")

    row = (
        await session.execute(
            select(ContentTemplate)
            .where(ContentTemplate.id == template_id)
            .where(ContentTemplate.published.is_(True))
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found.")

    if variant == "thumbnail":
        key = row.thumbnail_s3_key or (
            row.s3_key if row.kind == "image" else None
        )
        if not key:
            raise HTTPException(
                status_code=404,
                detail="No thumbnail available for this template.",
            )
    else:
        key = row.s3_key
        if not key:
            raise HTTPException(status_code=404, detail="Template has no asset.")

    from app.services.s3_storage import s3_client  # noqa: PLC0415

    try:
        client = s3_client(settings)
        obj = client.get_object(Bucket=bucket, Key=key)
    except Exception as e:  # noqa: BLE001 — boto raises a wide set of exceptions
        logger.exception("templates asset: S3 get_object failed key=%s", key)
        raise HTTPException(
            status_code=502, detail=f"Could not read asset from S3: {e}"
        ) from e

    body = obj["Body"]
    media_type = (
        obj.get("ContentType")
        or row.content_type
        or ("image/jpeg" if variant == "thumbnail" else "application/octet-stream")
    )

    declared_len = obj.get("ContentLength")
    if isinstance(declared_len, int) and declared_len > _MAX_ASSET_BYTES:
        raise HTTPException(status_code=413, detail="Asset too large.")

    def _stream() -> Any:
        # Bounded streaming — defend against unexpectedly huge objects even
        # if ContentLength is missing or lies.
        sent = 0
        try:
            for chunk in body.iter_chunks(chunk_size=64 * 1024):
                sent += len(chunk)
                if sent > _MAX_ASSET_BYTES:
                    logger.warning(
                        "templates asset: aborting stream over size cap key=%s",
                        key,
                    )
                    return
                yield chunk
        finally:
            try:
                body.close()
            except Exception:  # noqa: BLE001
                pass

    headers = {
        "Cache-Control": "public, max-age=300",
        "X-Content-Type-Options": "nosniff",
    }
    if isinstance(declared_len, int):
        headers["Content-Length"] = str(declared_len)

    return StreamingResponse(_stream(), media_type=media_type, headers=headers)
