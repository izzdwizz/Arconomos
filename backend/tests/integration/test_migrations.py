"""Runs the real Alembic migrations against a throwaway, dockerized Postgres — the CI
pipeline's "backend integration" stage. Needs Docker; not part of the fast unit run.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from app.db.models import User

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_url() -> str:
    with PostgresContainer("postgres:16-alpine") as container:
        yield container.get_connection_url().replace("psycopg2", "psycopg")


def test_migrations_apply_cleanly_and_orm_roundtrips(postgres_url: str) -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(postgres_url)
    session = sessionmaker(bind=engine)()
    try:
        user = User(privy_id="integration-test", wallet="0xINTEGRATION")
        session.add(user)
        session.commit()

        fetched = session.execute(select(User).where(User.privy_id == "integration-test")).scalar_one()
        assert fetched.wallet == "0xINTEGRATION"
    finally:
        session.close()

    # Downgrading back to nothing must also be clean -- catches migrations that can't be undone.
    command.downgrade(alembic_cfg, "base")
