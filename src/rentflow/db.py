from contextlib import contextmanager
import sqlite3
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def make_engine(data):
    if sqlite3.sqlite_version_info < (3, 51, 3):
        raise RuntimeError(
            "SQLite >= 3.51.3 erforderlich. Bitte die RentFlow-Laufzeit über LD_LIBRARY_PATH laden."
        )
    data.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{data / 'rentflow.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )

    @event.listens_for(engine, "connect")
    def configure(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA synchronous=FULL")

    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    return engine


@contextmanager
def transaction(engine):
    with Session(engine, expire_on_commit=False) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
