"""Add image_url to watch_items.

Revision ID: 20260413_0003
Revises: 20260413_0002
Create Date: 2026-04-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260413_0003"
down_revision = "20260413_0002"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [column["name"] for column in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not _has_column("watch_items", "image_url"):
        op.add_column("watch_items", sa.Column("image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("watch_items", "image_url"):
        op.drop_column("watch_items", "image_url")
