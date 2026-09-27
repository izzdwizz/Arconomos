from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.main import app
from app.db.models import Base
from app.db.session import get_db, make_engine


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def stub_auth_header(privy_id: str, wallet: str) -> dict[str, str]:
    return {"Authorization": f"Bearer stub:{privy_id}:{wallet}"}
