"""Builds the snapshot the agent's "Observe" step hands to forecasting and the model:
bucket balances, bills and goals due soon, and recent income history. Pure DB reads --
the chain is the source of truth, but the indexer keeps this cache current (see PRD design
rule in app/db/models.py), so the agent never has to make a live chain call just to plan.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bill, BucketBalance, Deposit, Goal, Vault

BUCKETS = ["Tax", "Bills", "Goals", "OwnerPay", "Buffer", "Savings"]


@dataclass(frozen=True)
class Snapshot:
    vault_id: str
    bucket_balances: dict[str, int]
    bills_due_soon: list[dict[str, Any]] = field(default_factory=list)
    goals: list[dict[str, Any]] = field(default_factory=list)
    weekly_income_history: list[float] = field(default_factory=list)


def build_snapshot(db: Session, vault: Vault, bills_horizon_days: int = 20, income_weeks: int = 12) -> Snapshot:
    balance_rows = db.execute(select(BucketBalance).where(BucketBalance.vault_id == vault.id)).scalars().all()
    balances_by_bucket = {row.bucket: row.amount for row in balance_rows}
    bucket_balances = {bucket: balances_by_bucket.get(bucket, 0) for bucket in BUCKETS}

    now = datetime.now(UTC)
    cutoff = now + timedelta(days=bills_horizon_days)
    bill_rows = (
        db.execute(
            select(Bill).where(Bill.vault_id == vault.id, Bill.due_date >= now, Bill.due_date <= cutoff)
        )
        .scalars()
        .all()
    )
    bills_due_soon = [
        {"id": bill.id, "name": bill.name, "amount": bill.amount, "due_date": bill.due_date.isoformat()}
        for bill in bill_rows
    ]

    goal_rows = db.execute(select(Goal).where(Goal.vault_id == vault.id)).scalars().all()
    goals = [
        {
            "id": goal.id,
            "name": goal.name,
            "target_amount": goal.target_amount,
            "target_date": goal.target_date.isoformat(),
            "priority": goal.priority,
        }
        for goal in goal_rows
    ]

    since = now - timedelta(weeks=income_weeks)
    income_deposits = (
        db.execute(
            select(Deposit).where(
                Deposit.vault_id == vault.id, Deposit.kind == "income", Deposit.created_at >= since
            )
        )
        .scalars()
        .all()
    )
    weekly_income_history = _bucket_deposits_into_weeks(income_deposits, since, now)

    return Snapshot(
        vault_id=vault.id,
        bucket_balances=bucket_balances,
        bills_due_soon=bills_due_soon,
        goals=goals,
        weekly_income_history=weekly_income_history,
    )


def _bucket_deposits_into_weeks(deposits: Sequence[Deposit], since: datetime, now: datetime) -> list[float]:
    """Sums income deposits into fixed 7-day buckets from `since` to `now`, for
    app/agent/forecast.py's resampling (median with low/high bands over recent weeks)."""
    total_weeks = max(1, (now - since).days // 7)
    weeks = [0.0] * total_weeks
    for deposit in deposits:
        created_at = deposit.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        week_index = min(total_weeks - 1, int((created_at - since).days // 7))
        if week_index < 0:
            continue
        weeks[week_index] += deposit.amount
    return weeks
