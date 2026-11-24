"""Add saved marketplace searches, their listings, prices and alerts.

Revision ID: 20261123_0005
Revises: 20260413_0004
Create Date: 2026-11-23
"""

from __future__ import annotations

from alembic import op

from snipebot.persistence.models import Base

# revision identifiers, used by Alembic.
revision = "20261123_0005"
down_revision = "20260413_0004"
branch_labels = None
depends_on = None

# Parent tables first; downgrade drops in reverse order.
_TABLES = (
    "marketplace_searches",
    "marketplace_listings",
    "marketplace_listing_prices",
    "marketplace_alert_events",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in _TABLES:
        Base.metadata.tables[name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(_TABLES):
        Base.metadata.tables[name].drop(bind, checkfirst=True)
