"""Engine/session factory. The API depends on `get_db`; scripts and tests can call
`make_engine` directly with an override URL (e.g. a testcontainers Postgres, or SQLite)."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    if url.startswith("sqlite"):
        # A SQLite in-memory DB is per-connection; StaticPool keeps every checkout on the
        # same connection so tables created at setup are still there for later requests.
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url)


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _get_session_factory() -> sessionmaker[Session]:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine = make_engine()
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = _get_session_factory()()
    try:
        yield session
    finally:
        session.close()
