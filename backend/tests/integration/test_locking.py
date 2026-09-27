"""Needs a real Postgres -- pg_advisory_lock has no SQLite equivalent."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from app.agent.locking import vault_lock

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def db_sessions():
    with PostgresContainer("postgres:16-alpine") as container:
        url = container.get_connection_url().replace("psycopg2", "psycopg")
        engine = create_engine(url)
        session_factory = sessionmaker(bind=engine)
        # Two separate connections/sessions, simulating two agent worker processes.
        yield session_factory(), session_factory()


def test_second_worker_cannot_acquire_lock_held_by_first(db_sessions) -> None:
    worker_a, worker_b = db_sessions

    with vault_lock(worker_a, "vault-123") as a_acquired:
        assert a_acquired is True
        with vault_lock(worker_b, "vault-123") as b_acquired:
            assert b_acquired is False


def test_lock_is_released_after_the_with_block(db_sessions) -> None:
    worker_a, worker_b = db_sessions

    with vault_lock(worker_a, "vault-456") as acquired:
        assert acquired is True

    with vault_lock(worker_b, "vault-456") as acquired:
        assert acquired is True


def test_different_vaults_do_not_contend(db_sessions) -> None:
    worker_a, worker_b = db_sessions

    with vault_lock(worker_a, "vault-a") as a_acquired, vault_lock(worker_b, "vault-b") as b_acquired:
        assert a_acquired is True
        assert b_acquired is True
