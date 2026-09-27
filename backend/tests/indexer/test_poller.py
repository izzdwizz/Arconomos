import contextlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, BucketBalance, Deposit, IndexerCursor, User, Vault
from app.indexer.classify import DepositKind
from app.indexer.events import DepositedEvent
from app.indexer.poller import run_indexer_tick


@pytest.fixture(autouse=True)
def _stub_vault_lock(monkeypatch):
    """pg_advisory_lock has no SQLite equivalent; its real behavior is covered by
    tests/integration/test_locking.py against a real Postgres. Here it's a pure pass-
    through so the poller's own dedup/routing logic can be tested without Docker."""

    @contextlib.contextmanager
    def fake_vault_lock(db, vault_id):
        yield True

    monkeypatch.setattr("app.indexer.poller.vault_lock", fake_vault_lock)


class FakeChainClient:
    def __init__(self, events: list[DepositedEvent], block_number: int, bucket_balances: dict[str, list[int]]) -> None:
        self._events = events
        self._block_number = block_number
        self._bucket_balances = bucket_balances

        class _Eth:
            def __init__(self, outer: "FakeChainClient") -> None:
                self._outer = outer

            @property
            def block_number(self) -> int:
                return self._outer._block_number

        class _W3:
            def __init__(self, outer: "FakeChainClient") -> None:
                self.eth = _Eth(outer)

        self.w3 = _W3(self)

    def get_all_deposited_events(self, from_block: int, to_block: int) -> list[DepositedEvent]:
        return [e for e in self._events if from_block <= e.block_number <= to_block]

    def get_bucket_balances(self, vault_address: str) -> list[int]:
        return self._bucket_balances[vault_address]


class FakeSigner:
    address = "0xOPERATOR"


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _make_vault(db, privy_id: str, vault_addr: str) -> Vault:
    user = User(privy_id=privy_id, wallet=f"0x{privy_id}")
    db.add(user)
    db.flush()
    vault = Vault(
        user_id=user.id,
        vault_addr=vault_addr,
        income_inbox=f"0xINCOME_{privy_id}",
        topup_inbox=f"0xTOPUP_{privy_id}",
        payout_addr=f"0xPAYOUT_{privy_id}",
        deployed_tx=f"0xDEPLOY_{privy_id}",
    )
    db.add(vault)
    db.commit()
    return vault


def _monkeypatch_scanner(monkeypatch, events: list[DepositedEvent]) -> None:
    def fake_scan_all(client, from_block, to_block):
        return [e for e in events if from_block <= e.block_number <= to_block]

    monkeypatch.setattr("app.indexer.poller.scan_all_deposited_events", fake_scan_all)


def test_indexer_tick_records_deposit_and_triggers_cycle_for_that_vault(monkeypatch):
    session_factory = _session_factory()
    db = session_factory()
    vault_a = _make_vault(db, "alice", "0xVAULTA")
    _make_vault(db, "bob", "0xVAULTB")  # exists but gets no deposit; must get no cycle either

    event = DepositedEvent(
        tx_hash="0xtx1",
        log_index=0,
        block_number=5,
        vault_address="0xVAULTA",
        inbox="0xINCOME_alice",
        kind=DepositKind.INCOME,
        amount=100_000000,
        src_tx="0x00",
    )
    _monkeypatch_scanner(monkeypatch, [event])

    chain = FakeChainClient(
        events=[event],
        block_number=10,
        bucket_balances={"0xVAULTA": [20_000000, 20_000000, 20_000000, 15_000000, 15_000000, 10_000000]},
    )

    triggered_for: list[str] = []

    def fake_trigger(db_arg, chain_arg, signer_arg, vault_arg, trigger, model_client, execute_action_fn):
        triggered_for.append(vault_arg.id)

    result = run_indexer_tick(
        db, chain, FakeSigner(), model_client=object(), chain_id=31337, execute_action_fn=lambda *a: "0x",
        trigger_deposit_cycle=fake_trigger,
    )

    assert result == {vault_a.id: 1}
    assert triggered_for == [vault_a.id]  # vault_b got no deposit, no cycle for it

    deposit = db.execute(select(Deposit).where(Deposit.vault_id == vault_a.id)).scalar_one()
    assert deposit.tx_hash == "0xtx1"
    assert deposit.kind == "income"

    balance_row = db.execute(
        select(BucketBalance).where(BucketBalance.vault_id == vault_a.id, BucketBalance.bucket == "Tax")
    ).scalar_one()
    assert balance_row.amount == 20_000000

    cursor = db.get(IndexerCursor, 31337)
    assert cursor.last_block == 10


def test_indexer_tick_is_idempotent_on_reprocessing(monkeypatch):
    session_factory = _session_factory()
    db = session_factory()
    vault = _make_vault(db, "carol", "0xVAULTC")

    event = DepositedEvent(
        tx_hash="0xtx2",
        log_index=0,
        block_number=3,
        vault_address="0xVAULTC",
        inbox="0xINCOME_carol",
        kind=DepositKind.TRANSFER,
        amount=50_000000,
        src_tx="0x00",
    )
    _monkeypatch_scanner(monkeypatch, [event])
    chain = FakeChainClient(events=[event], block_number=5, bucket_balances={"0xVAULTC": [0, 0, 0, 0, 50_000000, 0]})

    calls: list[str] = []

    def fake_trigger(db_arg, chain_arg, signer_arg, vault_arg, trigger, model_client, execute_action_fn):
        calls.append(vault_arg.id)

    run_indexer_tick(
        db, chain, FakeSigner(), model_client=object(), chain_id=1, execute_action_fn=lambda *a: "0x",
        trigger_deposit_cycle=fake_trigger,
    )
    assert len(db.execute(select(Deposit)).scalars().all()) == 1

    # Simulate a reorg rewinding the cursor: the next tick rescans a range that includes
    # the already-recorded event's block. The DB's unique constraint on (tx_hash,
    # log_index) must stop it from being inserted twice or re-triggering the agent.
    db.get(IndexerCursor, 1).last_block = 0
    db.commit()

    result_second = run_indexer_tick(
        db, chain, FakeSigner(), model_client=object(), chain_id=1, execute_action_fn=lambda *a: "0x",
        trigger_deposit_cycle=fake_trigger,
    )

    assert result_second == {}  # the one deposit found was a duplicate, so nothing "new"
    assert calls == [vault.id]  # only triggered once, from the first tick
    assert len(db.execute(select(Deposit)).scalars().all()) == 1
