"""Proves the indexer's chain-wide scan (ChainClient.get_all_deposited_events) actually
finds Deposited events from multiple, independently-deployed vaults in one call, and that
run_indexer_tick correctly routes each to its own vault, records it, and triggers that
vault's agent cycle -- end to end, against a real (local) chain.
"""

from __future__ import annotations

import contextlib
import subprocess
import time
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from web3 import Web3

from app.agent.model_client import ScriptedModelClient
from app.chain.client import ChainClient
from app.chain.signer import LocalKeySigner
from app.db.models import Base, Deposit, User, Vault
from app.indexer.poller import run_indexer_tick

from .anvil_deploy import DEPLOYER_ADDRESS, OPERATOR_PRIVATE_KEY, deploy_stack

pytestmark = pytest.mark.integration

ANVIL_PORT = 8551
ANVIL_URL = f"http://127.0.0.1:{ANVIL_PORT}"


@pytest.fixture(scope="module")
def anvil_url() -> Generator[str, None, None]:
    proc = subprocess.Popen(
        ["anvil", "--port", str(ANVIL_PORT), "--silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        w3 = Web3(Web3.HTTPProvider(ANVIL_URL))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if w3.is_connected():
                break
            time.sleep(0.2)
        yield ANVIL_URL
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _make_db_row(db, vault_addr: str, income_inbox: str, privy_id: str) -> Vault:
    user = User(privy_id=privy_id, wallet=f"0x{privy_id}")
    db.add(user)
    db.flush()
    vault_row = Vault(
        user_id=user.id,
        vault_addr=vault_addr,
        income_inbox=income_inbox,
        topup_inbox=income_inbox,  # unused by this test
        payout_addr=DEPLOYER_ADDRESS,
        deployed_tx="0xDEPLOYTX",
    )
    db.add(vault_row)
    db.commit()
    return vault_row


def test_indexer_tick_finds_deposits_across_two_independently_deployed_vaults(
    anvil_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # This test's DB is SQLite (its focus is the chain-side scan, proven against real
    # anvil); pg_advisory_lock has no SQLite equivalent. The lock's own behavior is
    # covered against real Postgres by tests/integration/test_locking.py.
    @contextlib.contextmanager
    def fake_vault_lock(db: object, vault_id: str) -> Generator[bool, None, None]:
        yield True

    monkeypatch.setattr("app.indexer.poller.vault_lock", fake_vault_lock)

    w3 = Web3(Web3.HTTPProvider(anvil_url))
    client = ChainClient(w3)

    stack_one = deploy_stack(w3)
    stack_two = deploy_stack(w3)  # a second, fully independent vault + inbox pair

    stack_one.usdc.functions.mint(stack_one.income_inbox_address, 100_000000).transact({"from": DEPLOYER_ADDRESS})
    stack_two.usdc.functions.mint(stack_two.income_inbox_address, 250_000000).transact({"from": DEPLOYER_ADDRESS})

    client.inbox(stack_one.income_inbox_address).functions.sweep().transact({"from": DEPLOYER_ADDRESS})
    client.inbox(stack_two.income_inbox_address).functions.sweep().transact({"from": DEPLOYER_ADDRESS})

    # anvil's log-bloom index lags one block behind a topic-filtered eth_getLogs query
    # immediately after mining; one empty block flushes it. Confirmed anvil-only quirk --
    # see the chain-client debugging notes; production polling against a real RPC just
    # naturally runs a tick or two after the block that contains the deposit.
    w3.provider.make_request("anvil_mine", [])

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    vault_one_row = _make_db_row(db, stack_one.vault_address, stack_one.income_inbox_address, "poller1")
    vault_two_row = _make_db_row(db, stack_two.vault_address, stack_two.income_inbox_address, "poller2")

    triggered_vault_ids: list[str] = []

    def fake_trigger(db_arg, chain_arg, signer_arg, vault_arg, trigger, model_client, execute_action_fn):
        triggered_vault_ids.append(vault_arg.id)

    signer = LocalKeySigner(OPERATOR_PRIVATE_KEY)
    result = run_indexer_tick(
        db,
        client,
        signer,
        ScriptedModelClient(),
        chain_id=w3.eth.chain_id,
        execute_action_fn=lambda *a: "0x",
        trigger_deposit_cycle=fake_trigger,
    )

    assert result == {vault_one_row.id: 1, vault_two_row.id: 1}
    assert set(triggered_vault_ids) == {vault_one_row.id, vault_two_row.id}

    deposits = db.execute(select(Deposit)).scalars().all()
    assert len(deposits) == 2
    amounts_by_vault = {d.vault_id: d.amount for d in deposits}
    assert amounts_by_vault[vault_one_row.id] == 100_000000
    assert amounts_by_vault[vault_two_row.id] == 250_000000

    # A second tick with nothing new must find nothing and trigger nothing again.
    result_second = run_indexer_tick(
        db,
        client,
        signer,
        ScriptedModelClient(),
        chain_id=w3.eth.chain_id,
        execute_action_fn=lambda *a: "0x",
        trigger_deposit_cycle=fake_trigger,
    )
    assert result_second == {}
    assert len(triggered_vault_ids) == 2
