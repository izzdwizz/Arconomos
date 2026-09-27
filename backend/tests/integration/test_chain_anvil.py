"""Proves the chain client against a real (local) chain: deploy the full stack on anvil,
deposit through an inbox, read the resulting event back through the indexer's scanner, then
push an agent-approved action through app.chain.actions and confirm it landed on-chain.
Needs `anvil` on PATH (installed via foundryup) -- not part of the fast unit run.
"""

from __future__ import annotations

import contextlib
import subprocess
import time
from collections.abc import Generator

import pytest
from web3 import Web3

from app.agent.policy import ActionType, ProposedAction
from app.chain.actions import execute_action
from app.chain.client import ChainClient
from app.chain.signer import LocalKeySigner
from app.indexer.classify import DepositKind
from app.indexer.events import DepositedEvent
from app.indexer.scanner import scan_deposited_events

from .anvil_deploy import OPERATOR_PRIVATE_KEY, deploy_stack

pytestmark = pytest.mark.integration

ANVIL_PORT = 8548
ANVIL_URL = f"http://127.0.0.1:{ANVIL_PORT}"


def _scan_with_retry(client: ChainClient, vault_address: str, attempts: int = 5) -> list[DepositedEvent]:
    """anvil's eth_getLogs can very occasionally lag one tick behind a just-mined block
    on the same connection; the production indexer polls in a loop anyway, so a short
    retry here is a faithful (not a papered-over) reproduction of that, not a test hack
    hiding a real bug."""
    for attempt in range(attempts):
        events = scan_deposited_events(client, vault_address, from_block=0, to_block=client.w3.eth.block_number)
        if events:
            return events
        if attempt < attempts - 1:
            time.sleep(0.2)
    return []


@pytest.fixture(scope="module")
def anvil_url() -> Generator[str, None, None]:
    proc = subprocess.Popen(
        ["anvil", "--port", str(ANVIL_PORT), "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        w3 = Web3(Web3.HTTPProvider(ANVIL_URL))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with contextlib.suppress(Exception):  # anvil not accepting connections yet
                if w3.is_connected():
                    break
            time.sleep(0.2)
        else:
            raise RuntimeError("anvil did not become ready in time")
        yield ANVIL_URL
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_deposit_sweep_and_operator_action_roundtrip_on_chain(anvil_url: str) -> None:
    client = ChainClient(Web3(Web3.HTTPProvider(anvil_url)))
    stack = deploy_stack(client.w3)

    income_amount = 1_000 * 10**6  # 1,000 USDC
    stack.usdc.functions.mint(stack.income_inbox_address, income_amount).transact(
        {"from": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"}
    )
    inbox = client.inbox(stack.income_inbox_address)
    sweep_tx = inbox.functions.sweep().transact({"from": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"})
    client.w3.eth.wait_for_transaction_receipt(sweep_tx)

    events = _scan_with_retry(client, stack.vault_address)

    assert len(events) == 1
    assert events[0].kind == DepositKind.INCOME
    assert events[0].amount == income_amount
    assert events[0].inbox.lower() == stack.income_inbox_address.lower()

    # The mechanical allocation already happened inside notifyDeposit; confirm the split
    # actually landed in the buckets before testing the agent's own on-chain action.
    tax_balance, *_ = client.get_bucket_balances(stack.vault_address)
    assert tax_balance == (income_amount * 2000) // 10_000  # 20% tax floor from deployVault

    # Now push an agent-approved adjust_split through the real signing path, using the
    # operator key set at deploy time -- this is what app/agent/planner.py + policy.py hand
    # to app/chain/actions.py once a proposal clears the guardrail check.
    operator_signer = LocalKeySigner(OPERATOR_PRIVATE_KEY)
    old_bps = client.get_split_bps(stack.vault_address)
    new_bps = {
        "Tax": old_bps[0],
        "Bills": old_bps[1] + 500,
        "Goals": old_bps[2],
        "OwnerPay": old_bps[3],
        "Buffer": old_bps[4] - 500,
        "Savings": old_bps[5],
    }
    action = ProposedAction(
        type=ActionType.ADJUST_SPLIT,
        params={"new_bps": new_bps},
        reason="rent is due soon, raising Bills ahead of it",
    )

    tx_hash = execute_action(client, operator_signer, stack.vault_address, action)
    client.w3.eth.wait_for_transaction_receipt(tx_hash)

    updated_bps = client.get_split_bps(stack.vault_address)
    assert updated_bps[1] == old_bps[1] + 500
    assert updated_bps[4] == old_bps[4] - 500


def test_operator_cannot_draw_down_tax_via_rebalance_on_chain(anvil_url: str) -> None:
    client = ChainClient(Web3(Web3.HTTPProvider(anvil_url)))
    stack = deploy_stack(client.w3)

    income_amount = 500 * 10**6
    stack.usdc.functions.mint(stack.income_inbox_address, income_amount).transact(
        {"from": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"}
    )
    inbox = client.inbox(stack.income_inbox_address)
    sweep_tx = inbox.functions.sweep().transact({"from": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"})
    client.w3.eth.wait_for_transaction_receipt(sweep_tx)

    operator_signer = LocalKeySigner(OPERATOR_PRIVATE_KEY)
    action = ProposedAction(
        type=ActionType.REBALANCE,
        params={"from_bucket": "Tax", "to_bucket": "Bills", "amount": 1},
        reason="attempted misuse",
    )

    from app.chain.client import SimulationRevertedError

    with pytest.raises(SimulationRevertedError, match="operator cannot draw down Tax"):
        execute_action(client, operator_signer, stack.vault_address, action)
