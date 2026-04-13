from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from snipebot.core.config import get_settings
from snipebot.persistence.models import Base

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _ensure_sqlite_parent_dir(settings.db_url)
        _engine = create_engine(
            settings.db_url,
            connect_args={"check_same_thread": False} if settings.is_sqlite else {},
            future=True,
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autocommit=False, autoflush=False, future=True
        )
    return _SessionLocal


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())
    _ensure_legacy_columns()


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_db_ready() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _ensure_sqlite_parent_dir(db_url: str) -> None:
    if not db_url.startswith("sqlite"):
        return

    db_path = db_url.replace("sqlite:///", "", 1)
    if db_path == ":memory:":
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _ensure_legacy_columns() -> None:
    settings = get_settings()
    if not settings.is_sqlite:
        return

    with get_engine().begin() as connection:
        rows = connection.execute(text("PRAGMA table_info('watch_items')")).fetchall()
        existing_columns = {row[1] for row in rows}

        if "notes" not in existing_columns:
            connection.execute(text("ALTER TABLE watch_items ADD COLUMN notes TEXT"))

        if "archived_at" not in existing_columns:
            connection.execute(
                text("ALTER TABLE watch_items ADD COLUMN archived_at DATETIME")
            )

        if "consecutive_failure_count" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE watch_items ADD COLUMN consecutive_failure_count INTEGER NOT NULL DEFAULT 0"
                )
            )

        if "dead_lettered_at" not in existing_columns:
            connection.execute(
                text("ALTER TABLE watch_items ADD COLUMN dead_lettered_at DATETIME")
            )

        if "dead_letter_reason" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE watch_items ADD COLUMN dead_letter_reason VARCHAR(255)"
                )
            )

        if "image_url" not in existing_columns:
            connection.execute(
                text("ALTER TABLE watch_items ADD COLUMN image_url TEXT")
            )

        alert_rows = connection.execute(
            text("PRAGMA table_info('alert_events')")
        ).fetchall()
        alert_columns = {row[1] for row in alert_rows}
        if "price_check_checked_at" not in alert_columns:
            connection.execute(
                text(
                    "ALTER TABLE alert_events ADD COLUMN price_check_checked_at DATETIME"
                )
            )
