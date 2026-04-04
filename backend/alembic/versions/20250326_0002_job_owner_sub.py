"""job owner_sub for OAuth-scoped media

Revision ID: 0002_owner_sub
Revises: 0001_initial
Create Date: 2025-03-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_owner_sub"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("owner_sub", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "owner_sub")
