from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


def build_engine(url: str) -> Engine:
    """SQLite is explicitly available to tests; application settings require PostgreSQL."""
    dialect = make_url(url).get_backend_name()
    if dialect == "sqlite":
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_timeout=5,
        connect_args={"connect_timeout": 5},
        hide_parameters=True,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db(request: Request) -> Generator[Session]:
    with request.app.state.session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
