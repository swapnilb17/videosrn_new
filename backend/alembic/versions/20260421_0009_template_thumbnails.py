"""content_templates: add thumbnail_s3_key for video poster frames

Revision ID: 0009_template_thumbnails
Revises: 0008_content_templates
Create Date: 2026-04-21

Single nullable column. Backfill happens lazily via the admin
``regenerate-thumbnail`` endpoint; existing rows continue to work
unchanged with the column null (clients fall back to a black poster).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_template_thumbnails"
down_revision: Union[str, None] = "0008_content_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_templates",
        sa.Column("thumbnail_s3_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_templates", "thumbnail_s3_key")
