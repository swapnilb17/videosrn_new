import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class MediaItem(Base):
    """Tracks every generated artifact (video, image, voice) per user for the media library."""

    __tablename__ = "media_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    media_url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_service: Mapped[str] = mapped_column(String(64), nullable=False)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    script: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tts_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    visual_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visual_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    branding_logo_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Google OIDC "sub" when job was created with OAuth on; used to scope /media access.
    owner_sub: Mapped[str | None] = mapped_column(String(128), nullable=True)
    s3_keys: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
