"""Append-only decision log: a hash chain, so no entry can be edited or removed unnoticed.

Once a day the agent writes the latest hash to Arc's Memo contract (see app/chain), so the
whole log can be checked against the chain independently of our own database.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

GENESIS_HASH = "0" * 64


@dataclass
class DecisionEntry:
    id: int
    trigger: str
    snapshot: dict[str, Any]
    proposed: list[dict[str, Any]]
    policy_result: dict[str, Any]
    reason: str
    prev_hash: str
    hash: str = field(init=False)
    tx_hash: str | None = None
    signature: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        self.snapshot = copy.deepcopy(self.snapshot)
        self.proposed = copy.deepcopy(self.proposed)
        self.policy_result = copy.deepcopy(self.policy_result)
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = {
            "id": self.id,
            "trigger": self.trigger,
            "snapshot": self.snapshot,
            "proposed": self.proposed,
            "policy_result": self.policy_result,
            "reason": self.reason,
            "prev_hash": self.prev_hash,
            "created_at": self.created_at,
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()


class DecisionLog:
    """In-memory chain; a real deployment persists entries to the `decisions` table and
    reconstructs `prev_hash` from the last row for that vault.
    """

    def __init__(self) -> None:
        self._entries: list[DecisionEntry] = []

    def append(
        self,
        trigger: str,
        snapshot: dict[str, Any],
        proposed: list[dict[str, Any]],
        policy_result: dict[str, Any],
        reason: str,
    ) -> DecisionEntry:
        prev_hash = self._entries[-1].hash if self._entries else GENESIS_HASH
        entry = DecisionEntry(
            id=len(self._entries),
            trigger=trigger,
            snapshot=snapshot,
            proposed=proposed,
            policy_result=policy_result,
            reason=reason,
            prev_hash=prev_hash,
        )
        self._entries.append(entry)
        return entry

    def attach_tx_hash(self, entry_id: int, tx_hash: str) -> None:
        self._entries[entry_id].tx_hash = tx_hash

    def entries(self) -> list[DecisionEntry]:
        return list(self._entries)

    def verify_chain(self) -> bool:
        """Detects tampering: recomputes each hash and checks prev_hash linkage."""
        prev_hash = GENESIS_HASH
        for entry in self._entries:
            if entry.prev_hash != prev_hash:
                return False
            if entry.hash != entry._compute_hash():
                return False
            prev_hash = entry.hash
        return True

    def latest_hash(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS_HASH
