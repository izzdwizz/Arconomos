"""SQLAlchemy models mirroring the PRD's data model.

The chain is the source of truth for balances; these tables are a cache plus the append-only
decision log. Any row here (other than `decisions`, which chains its own hashes) can in
principle be rebuilt from on-chain events.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    privy_id: Mapped[str] = mapped_column(unique=True, index=True)
    wallet: Mapped[str] = mapped_column(unique=True)
    country: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Vault(Base):
    __tablename__ = "vaults"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    vault_addr: Mapped[str] = mapped_column(unique=True)
    income_inbox: Mapped[str] = mapped_column(unique=True)
    topup_inbox: Mapped[str] = mapped_column(unique=True)
    payout_addr: Mapped[str]
    deployed_tx: Mapped[str]


class Rules(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    vault_id: Mapped[str] = mapped_column(ForeignKey("vaults.id"), unique=True)
    default_kind: Mapped[str] = mapped_column(default="transfer")
    # list of {"sender": str, "kind": str, "label": str}
    known_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class TaxSettings(Base):
    __tablename__ = "tax_settings"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    vault_id: Mapped[str] = mapped_column(ForeignKey("vaults.id"), unique=True)
    rate_bps: Mapped[int]
    delay_hours: Mapped[int] = mapped_column(default=72)
    source_default_id: Mapped[str | None] = mapped_column(ForeignKey("tax_defaults.id"), default=None)


class TaxDefault(Base):
    __tablename__ = "tax_defaults"
    __table_args__ = (UniqueConstraint("country", "income_type", name="uq_tax_default_country_income_type"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    country: Mapped[str]
    income_type: Mapped[str]
    rate_bps: Mapped[int]
    source_url: Mapped[str]
    retrieved_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    vault_id: Mapped[str] = mapped_column(ForeignKey("vaults.id"), index=True)
    name: Mapped[str]
    amount: Mapped[int]
    due_date: Mapped[datetime]
    recurrence: Mapped[str | None] = mapped_column(default=None)
    priority: Mapped[int] = mapped_column(default=0)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    vault_id: Mapped[str] = mapped_column(ForeignKey("vaults.id"), index=True)
    name: Mapped[str]
    target_amount: Mapped[int]
    target_date: Mapped[datetime]
    priority: Mapped[int] = mapped_column(default=0)


class Deposit(Base):
    __tablename__ = "deposits"
    __table_args__ = (UniqueConstraint("tx_hash", "log_index", name="uq_deposit_tx_log_index"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    vault_id: Mapped[str] = mapped_column(ForeignKey("vaults.id"), index=True)
    tx_hash: Mapped[str]
    log_index: Mapped[int]
    sender: Mapped[str]
    amount: Mapped[int]
    kind: Mapped[str]
    kind_source: Mapped[str]
    integration_event_id: Mapped[str | None] = mapped_column(ForeignKey("integration_events.id"), default=None)
    block_number: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Allocation(Base):
    __tablename__ = "allocations"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    deposit_id: Mapped[str] = mapped_column(ForeignKey("deposits.id"), index=True)
    bucket: Mapped[str]
    amount: Mapped[int]
    decision_id: Mapped[str | None] = mapped_column(ForeignKey("decisions.id"), default=None)


class BucketBalance(Base):
    __tablename__ = "bucket_balances"
    __table_args__ = (UniqueConstraint("vault_id", "bucket", name="uq_bucket_balance_vault_bucket"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    vault_id: Mapped[str] = mapped_column(ForeignKey("vaults.id"), index=True)
    bucket: Mapped[str]
    amount: Mapped[int]
    as_of_block: Mapped[int]


class ForecastRow(Base):
    __tablename__ = "forecasts"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    vault_id: Mapped[str] = mapped_column(ForeignKey("vaults.id"), index=True)
    run_at: Mapped[datetime] = mapped_column(server_default=func.now())
    week: Mapped[int]
    income_low: Mapped[float]
    income_mid: Mapped[float]
    income_high: Mapped[float]
    needed: Mapped[float]


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decisions_vault_id_created_at", "vault_id", "created_at"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    vault_id: Mapped[str] = mapped_column(ForeignKey("vaults.id"), index=True)
    prev_hash: Mapped[str]
    hash: Mapped[str] = mapped_column(unique=True)
    trigger: Mapped[str]
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    proposed: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    policy_result: Mapped[dict[str, Any]] = mapped_column(JSON)
    reason: Mapped[str]
    tx_hash: Mapped[str | None] = mapped_column(default=None)
    signature: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    vault_id: Mapped[str] = mapped_column(ForeignKey("vaults.id"), index=True)
    name: Mapped[str]
    key_hash: Mapped[str] = mapped_column(unique=True)


class IntegrationEvent(Base):
    __tablename__ = "integration_events"
    __table_args__ = (UniqueConstraint("integration_id", "tx_hash", name="uq_integration_event_tx_hash"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    integration_id: Mapped[str] = mapped_column(ForeignKey("integrations.id"), index=True)
    tx_hash: Mapped[str]
    label: Mapped[str]
    amount: Mapped[int]
    cost: Mapped[int]
    reference: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IndexerCursor(Base):
    __tablename__ = "indexer_cursor"

    chain_id: Mapped[int] = mapped_column(primary_key=True)
    last_block: Mapped[int]
