from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.model_client import ScriptedModelClient
from app.agent.scheduler import run_cycle_for_all_vaults
from app.db.models import Base, User, Vault


class FakeChainClient:
    def get_guardrails(self, vault_address: str) -> dict[str, int]:
        return {"min_tax_bps": 2000, "max_split_change_bps_per_week": 1000, "owner_pay_cap_per_period": 0, "buffer_floor": 0}

    def get_split_bps(self, vault_address: str) -> list[int]:
        return [2000, 2000, 2000, 1500, 1500, 1000]


class FakeSigner:
    address = "0xOPERATOR"


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _add_vault(session_factory, privy_id: str) -> str:
    db = session_factory()
    user = User(privy_id=privy_id, wallet=f"0x{privy_id}")
    db.add(user)
    db.flush()
    vault = Vault(
        user_id=user.id,
        vault_addr=f"0xVAULT_{privy_id}",
        income_inbox=f"0xINCOME_{privy_id}",
        topup_inbox=f"0xTOPUP_{privy_id}",
        payout_addr=f"0xPAYOUT_{privy_id}",
        deployed_tx=f"0xDEPLOY_{privy_id}",
    )
    db.add(vault)
    db.commit()
    vault_id = vault.id
    db.close()
    return vault_id


def test_runs_a_cycle_for_every_vault():
    session_factory = _session_factory()
    _add_vault(session_factory, "alice")
    _add_vault(session_factory, "bob")

    ran_for: list[str] = []

    def fake_run_cycle(db, chain_client, signer, vault, trigger, model_client, execute_action_fn):
        ran_for.append(vault.id)

    # sqlite has no pg_advisory_lock, so the lock helper is stubbed here; its own
    # behavior against real Postgres is covered by tests/integration/test_locking.py.
    @contextmanager
    def fake_vault_lock(db, vault_id):
        yield True

    with patch("app.agent.scheduler.run_cycle", fake_run_cycle), patch("app.agent.scheduler.vault_lock", fake_vault_lock):
        run_cycle_for_all_vaults(session_factory, FakeChainClient(), FakeSigner(), ScriptedModelClient(), "daily")

    assert len(ran_for) == 2


def test_skips_vault_whose_lock_is_held_by_another_worker():
    session_factory = _session_factory()
    _add_vault(session_factory, "carol")

    ran_for: list[str] = []

    def fake_run_cycle(db, chain_client, signer, vault, trigger, model_client, execute_action_fn):
        ran_for.append(vault.id)

    @contextmanager
    def fake_vault_lock(db, vault_id):
        yield False  # another worker holds it

    with patch("app.agent.scheduler.run_cycle", fake_run_cycle), patch("app.agent.scheduler.vault_lock", fake_vault_lock):
        run_cycle_for_all_vaults(session_factory, FakeChainClient(), FakeSigner(), ScriptedModelClient(), "daily")

    assert ran_for == []


def test_one_vault_failing_does_not_block_the_others():
    session_factory = _session_factory()
    _add_vault(session_factory, "dave")
    _add_vault(session_factory, "erin")

    ran_for: list[str] = []

    def fake_run_cycle(db, chain_client, signer, vault, trigger, model_client, execute_action_fn):
        if len(ran_for) == 0:
            ran_for.append(vault.id)
            raise RuntimeError("boom")
        ran_for.append(vault.id)

    @contextmanager
    def fake_vault_lock(db, vault_id):
        yield True

    with patch("app.agent.scheduler.run_cycle", fake_run_cycle), patch("app.agent.scheduler.vault_lock", fake_vault_lock):
        run_cycle_for_all_vaults(session_factory, FakeChainClient(), FakeSigner(), ScriptedModelClient(), "daily")

    assert len(ran_for) == 2
