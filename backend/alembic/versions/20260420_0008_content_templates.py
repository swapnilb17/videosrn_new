"""content_templates — admin-uploaded templates for user dashboards

Revision ID: 0008_content_templates
Revises: 0007_credit_codes
Create Date: 2026-04-20

One new table. No existing table is modified.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_content_templates"
down_revision: Union[str, None] = "0007_credit_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_templates",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column(
            "size_bytes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("tags", sa.String(length=256), nullable=True),
        sa.Column(
            "published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("s3_key", name="uq_content_templates_s3_key"),
        sa.CheckConstraint(
            "kind IN ('image','video')", name="ck_content_templates_kind"
        ),
        sa.CheckConstraint(
            "size_bytes >= 0", name="ck_content_templates_size_nonneg"
        ),
    )
    op.create_index(
        op.f("ix_content_templates_category"),
        "content_templates",
        ["category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_templates_language"),
        "content_templates",
        ["language"],
        unique=False,
    )
    op.create_index(
        op.f("ix_content_templates_published"),
        "content_templates",
        ["published"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_content_templates_published"), table_name="content_templates"
    )
    op.drop_index(
        op.f("ix_content_templates_language"), table_name="content_templates"
    )
    op.drop_index(
        op.f("ix_content_templates_category"), table_name="content_templates"
    )
    op.drop_table("content_templates")
