import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class User(Base):
    """Billing identity: credits + plan (free vs starter)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    google_sub: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)
    credit_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    signup_grant_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    starter_redeem_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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

    ledger_entries: Mapped[list["CreditLedger"]] = relationship(
        "CreditLedger",
        back_populates="user",
    )


class RazorpayPayment(Base):
    """Recorded Razorpay payment_ids for idempotent Starter bundle grants."""

    __tablename__ = "razorpay_payments"

    razorpay_payment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class CreditPromoRedemption(Base):
    """One row per promo code string — first successful redeem wins (global single-use)."""

    __tablename__ = "credit_promo_redemptions"

    code_normalized: Mapped[str] = mapped_column(String(64), primary_key=True)
    redeemed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credits_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class CreditLedger(Base):
    """Append-only credit movements."""

    __tablename__ = "credit_ledger"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="ledger_entries")


class CreditCode(Base):
    """Admin-issued credit code (catalog).

    A row here describes a single user-facing code string. Redemptions are
    tracked separately in :class:`CreditCodeRedemption` so multi-use codes
    can be supported without losing history.
    """

    __tablename__ = "credit_codes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    code_normalized: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    credits_each: Mapped[int] = mapped_column(Integer, nullable=False)
    # 0 means unlimited; default is single-use (matches legacy promo behaviour).
    max_redemptions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    redeemed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class CreditCodeRedemption(Base):
    """One row per (code, user) successful redemption.

    The composite primary key prevents the same user from redeeming the
    same code twice. A unique constraint on the parent table guarantees
    `code_normalized` matches at most one row in :class:`CreditCode`.
    """

    __tablename__ = "credit_code_redemptions"

    code_normalized: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("credit_codes.code_normalized", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    credits_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


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
