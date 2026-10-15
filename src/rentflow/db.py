from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session
class Base(DeclarativeBase): pass
def make_engine(data):
    data.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{data / 'rentflow.sqlite3'}", connect_args={"check_same_thread": False, "timeout": 15})
    @event.listens_for(engine, "connect")
    def configure(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA synchronous=FULL")
    with engine.connect() as conn: conn.exec_driver_sql("PRAGMA journal_mode=WAL")
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
