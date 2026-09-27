"""Dashboard summary: balance per bucket, plus the vault's addresses. Reads the
`bucket_balances` cache table -- populated by the indexer as it processes chain events --
rather than calling the chain directly from a request handler (see design rule in
app/db/models.py: the chain is the source of truth, Postgres is a cache).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BucketBalance, Vault
from app.db.session import get_db

from ..deps import get_current_vault

router = APIRouter(tags=["dashboard"])

BUCKETS = ["Tax", "Bills", "Goals", "OwnerPay", "Buffer", "Savings"]


@router.get("/v1/dashboard/summary")
def get_dashboard_summary(
    vault: Vault = Depends(get_current_vault),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = db.execute(select(BucketBalance).where(BucketBalance.vault_id == vault.id)).scalars().all()
    balances_by_bucket = {row.bucket: row.amount for row in rows}
    as_of_block = max((row.as_of_block for row in rows), default=0)

    balances = {bucket: balances_by_bucket.get(bucket, 0) for bucket in BUCKETS}
    return {
        "vault_addr": vault.vault_addr,
        "balances": balances,
        "total": sum(balances.values()),
        "as_of_block": as_of_block,
    }
