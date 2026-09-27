"""Deposit classification: known-source rule, then which address it arrived at, then default.

Inbox-tagged deposits never reach this — their kind comes from the chain event itself and
can't be spoofed. This module only classifies deposits that land straight on the vault.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DepositKind(str, Enum):
    INCOME = "income"
    TRANSFER = "transfer"


class KindSource(str, Enum):
    KNOWN_SOURCE = "known_source"
    DEFAULT = "default"


@dataclass(frozen=True)
class KnownSourceRule:
    sender: str
    kind: DepositKind
    label: str


@dataclass(frozen=True)
class ClassificationResult:
    kind: DepositKind
    kind_source: KindSource
    matched_rule: KnownSourceRule | None = None


def classify_direct_deposit(
    sender: str,
    known_sources: list[KnownSourceRule],
    default_kind: DepositKind,
) -> ClassificationResult:
    """Precedence for anything sent straight to the vault: known-source rule, then default."""
    sender_lower = sender.lower()
    for rule in known_sources:
        if rule.sender.lower() == sender_lower:
            return ClassificationResult(kind=rule.kind, kind_source=KindSource.KNOWN_SOURCE, matched_rule=rule)
    return ClassificationResult(kind=default_kind, kind_source=KindSource.DEFAULT)
