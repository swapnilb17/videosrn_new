"""credit_codes + credit_code_redemptions — admin-issued credit codes

Revision ID: 0007_credit_codes
Revises: 0006_razorpay_payments
Create Date: 2026-04-20

Adds two new tables to back the admin "Credit codes" page in the Enably
admin console. No existing tables are touched.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_credit_codes"
down_revision: Union[str, None] = "0006_razorpay_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_codes",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("code_normalized", sa.String(length=64), nullable=False),
        sa.Column("credits_each", sa.Integer(), nullable=False),
        sa.Column(
            "max_redemptions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "redeemed_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("campaign", sa.String(length=128), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_credit_codes_code"),
        sa.UniqueConstraint(
            "code_normalized", name="uq_credit_codes_code_normalized"
        ),
        sa.CheckConstraint("credits_each > 0", name="ck_credit_codes_credits_pos"),
        sa.CheckConstraint(
            "max_redemptions >= 0", name="ck_credit_codes_max_redemptions_nonneg"
        ),
        sa.CheckConstraint(
            "redeemed_count >= 0", name="ck_credit_codes_redeemed_count_nonneg"
        ),
    )
    op.create_index(
        op.f("ix_credit_codes_code_normalized"),
        "credit_codes",
        ["code_normalized"],
        unique=True,
    )

    op.create_table(
        "credit_code_redemptions",
        sa.Column("code_normalized", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("credits_amount", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["code_normalized"],
            ["credit_codes.code_normalized"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("code_normalized", "user_id"),
    )
    op.create_index(
        op.f("ix_credit_code_redemptions_user_id"),
        "credit_code_redemptions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_credit_code_redemptions_user_id"),
        table_name="credit_code_redemptions",
    )
    op.drop_table("credit_code_redemptions")
    op.drop_index(
        op.f("ix_credit_codes_code_normalized"), table_name="credit_codes"
    )
    op.drop_table("credit_codes")
