"""Turns a decoded `Deposited` event into a ledger-ready record.

Inbox-tagged deposits carry their kind in the event itself — set at the inbox's creation,
forwarded by `sweep()` — so the indexer just records it; nothing here re-derives or second
guesses that tag the way `classify_direct_deposit` does for untagged direct deposits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.indexer.classify import DepositKind


@dataclass(frozen=True)
class DepositedEvent:
    tx_hash: str
    log_index: int
    block_number: int
    vault_address: str
    inbox: str
    kind: DepositKind
    amount: int
    src_tx: str


def record_inbox_deposit(event: DepositedEvent) -> dict[str, Any]:
    """The kind on an inbox-forwarded deposit is authoritative: it came from the chain, not
    from any rule this backend evaluated, so it's recorded as-is."""
    return {
        "tx_hash": event.tx_hash,
        "log_index": event.log_index,
        "block_number": event.block_number,
        "sender": event.inbox,
        "amount": event.amount,
        "kind": event.kind,
        "kind_source": "inbox",
    }
