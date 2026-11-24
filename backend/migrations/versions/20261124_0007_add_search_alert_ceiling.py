"""Add the Telegram price ceiling to saved marketplace searches.

Revision ID: 20261124_0007
Revises: 20261124_0006
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20261124_0007"
down_revision = "20261124_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marketplace_searches",
        sa.Column("alert_max_price", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("marketplace_searches") as batch:
        batch.drop_column("alert_max_price")
