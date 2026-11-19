"""Store the first successful price on each watch item."""

import sqlalchemy as sa
from alembic import op

from snipebot.persistence.first_price import BACKFILL_FIRST_PRICE

revision = "20260413_0004"
down_revision = "20260413_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = sa.inspect(op.get_bind()).get_columns("watch_items")
    if not any(column["name"] == "first_price" for column in columns):
        op.add_column("watch_items", sa.Column("first_price", sa.Numeric(10, 2)))
    op.execute(sa.text(BACKFILL_FIRST_PRICE))


def downgrade() -> None:
    op.drop_column("watch_items", "first_price")
