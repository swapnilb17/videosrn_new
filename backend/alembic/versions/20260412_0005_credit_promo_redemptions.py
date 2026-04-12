"""credit_promo_redemptions — global single-use promo credit codes

Revision ID: 0005_credit_promo_redemptions
Revises: 0004_users_credits
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_credit_promo_redemptions"
down_revision: Union[str, None] = "0004_users_credits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_promo_redemptions",
        sa.Column("code_normalized", sa.String(length=64), nullable=False),
        sa.Column("redeemed_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("credits_amount", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["redeemed_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("code_normalized"),
    )


def downgrade() -> None:
    op.drop_table("credit_promo_redemptions")
