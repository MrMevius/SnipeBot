"""Search several platforms per saved search.

Adds SnipeBot's own filters to searches, one source row per searched platform
(copied from the existing single-platform searches) and the platform of each
recorded listing.

Revision ID: 20261125_0008
Revises: 20261124_0007
Create Date: 2026-11-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from snipebot.persistence.search_sources import COPY_LEGACY_SEARCH_SOURCES

# revision identifiers, used by Alembic.
revision = "20261125_0008"
down_revision = "20261124_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("marketplace_searches", sa.Column("filters_json", sa.Text(), nullable=True))
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "marketplace", sa.String(32), nullable=False, server_default="marktplaats"
        ),
    )
    op.add_column(
        "marketplace_listings",
        sa.Column("unverified_filters_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "marketplace_search_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "search_id",
            sa.Integer(),
            sa.ForeignKey("marketplace_searches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("marketplace", sa.String(32), nullable=False),
        sa.Column("query_json", sa.Text(), nullable=False),
        sa.Column("post_filters_json", sa.Text(), nullable=False),
        sa.Column("baseline_done", sa.Boolean(), nullable=False),
        sa.Column("id_watermark", sa.BigInteger(), nullable=True),
        sa.Column("last_total_count", sa.Integer(), nullable=True),
        sa.Column("last_fetched_count", sa.Integer(), nullable=True),
        sa.Column("last_complete", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(32), nullable=False),
        sa.Column("last_error_message", sa.String(512), nullable=True),
        sa.Column("consecutive_failure_count", sa.Integer(), nullable=False),
        sa.Column("check_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("search_id", "marketplace", name="uq_marketplace_search_source"),
    )
    op.create_index(
        "ix_marketplace_search_sources_search_id", "marketplace_search_sources", ["search_id"]
    )
    op.create_index(
        "ix_marketplace_search_sources_next_check_at",
        "marketplace_search_sources",
        ["next_check_at"],
    )
    op.execute(COPY_LEGACY_SEARCH_SOURCES)


def downgrade() -> None:
    op.drop_index("ix_marketplace_search_sources_next_check_at", "marketplace_search_sources")
    op.drop_index("ix_marketplace_search_sources_search_id", "marketplace_search_sources")
    op.drop_table("marketplace_search_sources")
    with op.batch_alter_table("marketplace_listings") as batch:
        batch.drop_column("unverified_filters_json")
        batch.drop_column("marketplace")
    with op.batch_alter_table("marketplace_searches") as batch:
        batch.drop_column("filters_json")
