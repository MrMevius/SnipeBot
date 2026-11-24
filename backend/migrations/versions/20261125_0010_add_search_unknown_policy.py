"""Per-search handling of listings that do not state a post-filtered value.

Revision ID: 20261125_0010
Revises: 20261125_0009
Create Date: 2026-11-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20261125_0010"
down_revision = "20261125_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marketplace_searches",
        sa.Column("unknown_policy", sa.String(16), nullable=False, server_default="include"),
    )


def downgrade() -> None:
    with op.batch_alter_table("marketplace_searches") as batch:
        batch.drop_column("unknown_policy")
