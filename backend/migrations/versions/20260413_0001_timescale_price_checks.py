"""Enable Timescale policies for price_checks on PostgreSQL.

Revision ID: 20260413_0001
Revises:
Create Date: 2026-04-13
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20260413_0001"
down_revision = None
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema = current_schema()
                AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    ).scalar_one()
    return bool(result)


def _is_hypertable(table_name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1
              FROM timescaledb_information.hypertables
              WHERE hypertable_schema = current_schema()
                AND hypertable_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    ).scalar_one()
    return bool(result)


def upgrade() -> None:
    if not _is_postgresql():
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    if not _table_exists("price_checks"):
        return

    # NOTE:
    # Timescale requires unique indexes (including PK) on hypertables to include
    # the partition key (`checked_at`). Current schema keeps `price_checks.id` as
    # standalone PK (referenced by `alert_events.price_check_id`). To avoid
    # hard-failing migration on existing installations, we attempt conversion and
    # gracefully skip if schema constraints are incompatible.
    op.execute(
        """
        DO $$
        BEGIN
          PERFORM create_hypertable('price_checks', 'checked_at', if_not_exists => TRUE, migrate_data => TRUE);
        EXCEPTION
          WHEN OTHERS THEN
            RAISE NOTICE 'Skipping price_checks hypertable conversion: %', SQLERRM;
        END
        $$;
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_checks_watch_item_checked_at_desc "
        "ON price_checks (watch_item_id, checked_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_checks_watch_item_checked_at_ok_priced "
        "ON price_checks (watch_item_id, checked_at DESC) "
        "WHERE status = 'ok' AND current_price IS NOT NULL"
    )

    if _is_hypertable("price_checks"):
        op.execute(
            "ALTER TABLE price_checks "
            "SET (timescaledb.compress, timescaledb.compress_segmentby = 'watch_item_id', "
            "timescaledb.compress_orderby = 'checked_at DESC')"
        )
        op.execute(
            "SELECT add_compression_policy('price_checks', INTERVAL '7 days', if_not_exists => TRUE)"
        )
        op.execute(
            "SELECT add_retention_policy('price_checks', INTERVAL '24 months', if_not_exists => TRUE)"
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    if _is_hypertable("price_checks"):
        op.execute("SELECT remove_retention_policy('price_checks', if_exists => TRUE)")
        op.execute(
            "SELECT remove_compression_policy('price_checks', if_exists => TRUE)"
        )
    op.execute("DROP INDEX IF EXISTS ix_price_checks_watch_item_checked_at_ok_priced")
    op.execute("DROP INDEX IF EXISTS ix_price_checks_watch_item_checked_at_desc")
