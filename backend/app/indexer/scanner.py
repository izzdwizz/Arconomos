"""Polls `Deposited` events off-chain and turns them into the same `DepositedEvent` shape
app/indexer/events.py already knows how to record. This is the piece that makes the
indexer's classification logic (tested against plain dataclasses in tests/indexer/)
actually run against a live chain.
"""

from __future__ import annotations

from typing import Any

from app.chain.client import ChainClient
from app.indexer.classify import DepositKind
from app.indexer.events import DepositedEvent

# Must match the Vault contract's `DepositKind` enum order: Transfer=0, Income=1.
_KIND_BY_INDEX = {0: DepositKind.TRANSFER, 1: DepositKind.INCOME}


def _to_deposited_event(log: Any, vault_address: str) -> DepositedEvent:
    args = log["args"]
    src_tx_bytes = args["srcTx"]
    return DepositedEvent(
        tx_hash=log["transactionHash"].hex(),
        log_index=log["logIndex"],
        block_number=log["blockNumber"],
        vault_address=vault_address,
        inbox=args["inbox"],
        kind=_KIND_BY_INDEX[args["kind"]],
        amount=args["amount"],
        src_tx=src_tx_bytes.hex() if hasattr(src_tx_bytes, "hex") else str(src_tx_bytes),
    )


def scan_deposited_events(client: ChainClient, vault_address: str, from_block: int, to_block: int) -> list[DepositedEvent]:
    raw_logs = client.get_deposited_events(vault_address, from_block, to_block)
    return [_to_deposited_event(log, vault_address) for log in raw_logs]


def scan_all_deposited_events(client: ChainClient, from_block: int, to_block: int) -> list[DepositedEvent]:
    """One call covers every vault: see ChainClient.get_all_deposited_events for why a
    single topic-only filter is enough to catch every vault's Deposited events."""
    raw_logs = client.get_all_deposited_events(from_block, to_block)
    return [_to_deposited_event(log, log["address"]) for log in raw_logs]
