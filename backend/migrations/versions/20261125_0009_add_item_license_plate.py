"""Store the license plate of archived listings (duplicates across platforms).

Revision ID: 20261125_0009
Revises: 20261125_0008
Create Date: 2026-11-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20261125_0009"
down_revision = "20261125_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("marketplace_items", sa.Column("license_plate", sa.String(16), nullable=True))
    op.create_index(
        "ix_marketplace_items_license_plate", "marketplace_items", ["license_plate"]
    )


def downgrade() -> None:
    op.drop_index("ix_marketplace_items_license_plate", "marketplace_items")
    with op.batch_alter_table("marketplace_items") as batch:
        batch.drop_column("license_plate")
