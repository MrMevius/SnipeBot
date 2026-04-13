"""Make price_checks schema Timescale-compatible and apply policies.

Revision ID: 20260413_0002
Revises: 20260413_0001
Create Date: 2026-04-13
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20260413_0002"
down_revision = "20260413_0001"
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
    if not _table_exists("price_checks") or not _table_exists("alert_events"):
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.execute(
        "ALTER TABLE alert_events "
        "ADD COLUMN IF NOT EXISTS price_check_checked_at TIMESTAMPTZ"
    )
    op.execute(
        """
        UPDATE alert_events ae
        SET price_check_checked_at = pc.checked_at
        FROM price_checks pc
        WHERE ae.price_check_id = pc.id
          AND ae.price_check_checked_at IS NULL
        """
    )

    op.execute(
        "ALTER TABLE alert_events DROP CONSTRAINT IF EXISTS alert_events_price_check_id_fkey"
    )

    op.execute("ALTER TABLE price_checks DROP CONSTRAINT IF EXISTS price_checks_pkey")
    op.execute(
        "ALTER TABLE price_checks "
        "ADD CONSTRAINT price_checks_pkey PRIMARY KEY (id, checked_at)"
    )

    op.execute(
        "ALTER TABLE alert_events "
        "ADD CONSTRAINT fk_alert_events_price_checks_composite "
        "FOREIGN KEY (price_check_id, price_check_checked_at) "
        "REFERENCES price_checks (id, checked_at) ON DELETE CASCADE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alert_events_price_check_composite "
        "ON alert_events (price_check_id, price_check_checked_at)"
    )

    if not _is_hypertable("price_checks"):
        op.execute(
            "SELECT create_hypertable('price_checks', 'checked_at', if_not_exists => TRUE, migrate_data => TRUE)"
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
    if not _table_exists("price_checks") or not _table_exists("alert_events"):
        return

    if _is_hypertable("price_checks"):
        op.execute("SELECT remove_retention_policy('price_checks', if_exists => TRUE)")
        op.execute(
            "SELECT remove_compression_policy('price_checks', if_exists => TRUE)"
        )

    op.execute(
        "ALTER TABLE alert_events DROP CONSTRAINT IF EXISTS fk_alert_events_price_checks_composite"
    )
    op.execute("DROP INDEX IF EXISTS ix_alert_events_price_check_composite")
