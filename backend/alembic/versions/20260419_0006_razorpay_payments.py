"""razorpay_payments — idempotent Starter bundle purchases

Revision ID: 0006_razorpay_payments
Revises: 0005_credit_promo_redemptions
Create Date: 2026-04-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_razorpay_payments"
down_revision: Union[str, None] = "0005_credit_promo_redemptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "razorpay_payments",
        sa.Column("razorpay_payment_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("razorpay_payment_id"),
    )
    op.create_index(
        op.f("ix_razorpay_payments_user_id"),
        "razorpay_payments",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_razorpay_payments_user_id"), table_name="razorpay_payments")
    op.drop_table("razorpay_payments")
