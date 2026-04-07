"""media_items table for per-user media library

Revision ID: 0003_media_items
Revises: 0002_owner_sub
Create Date: 2026-04-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_media_items"
down_revision: Union[str, None] = "0002_owner_sub"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_items",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("media_url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("source_service", sa.String(length=64), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_items_owner_email", "media_items", ["owner_email"])


def downgrade() -> None:
    op.drop_index("ix_media_items_owner_email", table_name="media_items")
    op.drop_table("media_items")
