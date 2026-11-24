"""Add the local archive of marketplace listings: items, versions, photos, prices.

Revision ID: 20261124_0006
Revises: 20261123_0005
Create Date: 2026-11-24
"""

from __future__ import annotations

from alembic import op

from snipebot.persistence.models import Base

# revision identifiers, used by Alembic.
revision = "20261124_0006"
down_revision = "20261123_0005"
branch_labels = None
depends_on = None

# Parent tables first; downgrade drops in reverse order.
_TABLES = (
    "marketplace_items",
    "marketplace_item_versions",
    "marketplace_item_images",
    "marketplace_item_prices",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in _TABLES:
        Base.metadata.tables[name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(_TABLES):
        Base.metadata.tables[name].drop(bind, checkfirst=True)
