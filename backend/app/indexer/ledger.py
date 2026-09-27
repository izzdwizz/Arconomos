"""Turns raw chain logs into ledger rows, idempotently.

The chain is the source of truth; Postgres is a cache. If the indexer's cursor is rewound
after a reorg and the same block range is processed again, no duplicate rows should appear —
`record_deposits` is keyed on (tx_hash, log_index), which is unique per log forever.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawDepositLog:
    tx_hash: str
    log_index: int
    inbox_or_vault: str
    sender: str
    amount: int
    block_number: int


@dataclass(frozen=True)
class DepositRow:
    tx_hash: str
    log_index: int
    sender: str
    amount: int
    block_number: int


class Ledger:
    """In-memory stand-in for the `deposits` table + `indexer_cursor` row."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, int], DepositRow] = {}
        self.last_block: int = 0

    def record_deposits(self, logs: list[RawDepositLog]) -> list[DepositRow]:
        """Returns only the rows newly inserted by this call (empty on a pure replay)."""
        newly_inserted: list[DepositRow] = []
        for log in logs:
            key = (log.tx_hash, log.log_index)
            if key in self._rows:
                continue
            row = DepositRow(
                tx_hash=log.tx_hash,
                log_index=log.log_index,
                sender=log.sender,
                amount=log.amount,
                block_number=log.block_number,
            )
            self._rows[key] = row
            newly_inserted.append(row)
            self.last_block = max(self.last_block, log.block_number)
        return newly_inserted

    def all_rows(self) -> list[DepositRow]:
        return list(self._rows.values())
