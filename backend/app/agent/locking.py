"""Postgres advisory locks: cheap mutual exclusion per vault so two agent workers never
run a cycle on the same vault at once, without a separate queue (PRD tech stack: "no extra
queue to run for 3-5 users"). A session-level advisory lock is released automatically if a
worker dies mid-cycle -- it doesn't need a heartbeat or an explicit unlock in that case.
"""

from __future__ import annotations

import hashlib
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session


def _lock_key(vault_id: str) -> int:
    """pg_advisory_lock takes a bigint; hash the vault's UUID down to a stable int64."""
    digest = hashlib.sha256(vault_id.encode()).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextmanager
def vault_lock(db: Session, vault_id: str) -> Generator[bool, None, None]:
    """Non-blocking: yields True if this worker acquired the lock (and holds it for the
    `with` block), False if another worker already has it -- the caller should skip this
    vault's cycle this tick rather than wait, since the next tick will just try again."""
    key = _lock_key(vault_id)
    acquired: bool = db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar_one()
    try:
        yield bool(acquired)
    finally:
        if acquired:
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
