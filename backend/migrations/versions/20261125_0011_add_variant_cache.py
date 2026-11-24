"""Cache of listing variants resolved from listing pages.

Revision ID: 20261125_0011
Revises: 20261125_0010
Create Date: 2026-11-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20261125_0011"
down_revision = "20261125_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_variant_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("marketplace", sa.String(32), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("variants", sa.String(64), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("marketplace", "item_id", name="uq_marketplace_variant_cache"),
    )


def downgrade() -> None:
    op.drop_table("marketplace_variant_cache")
