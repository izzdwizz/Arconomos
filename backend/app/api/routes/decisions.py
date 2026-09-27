from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Decision, Vault
from app.db.session import get_db

from ..deps import get_current_vault

router = APIRouter(tags=["decisions"])


def _serialize(decision: Decision) -> dict[str, Any]:
    return {
        "id": decision.id,
        "vault_id": decision.vault_id,
        "trigger": decision.trigger,
        "reason": decision.reason,
        "hash": decision.hash,
        "prev_hash": decision.prev_hash,
        "tx_hash": decision.tx_hash,
        "policy_result": decision.policy_result,
        "proposed": decision.proposed,
        "created_at": decision.created_at.isoformat(),
    }


@router.get("/v1/decisions")
def list_decisions(
    vault: Vault = Depends(get_current_vault),
    db: Session = Depends(get_db),
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = (
        db.execute(
            select(Decision).where(Decision.vault_id == vault.id).order_by(Decision.created_at.desc()).limit(limit)
        )
        .scalars()
        .all()
    )
    return [_serialize(row) for row in rows]


@router.get("/v1/decisions/{decision_id}")
def get_decision(
    decision_id: str,
    vault: Vault = Depends(get_current_vault),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    decision = db.execute(select(Decision).where(Decision.id == decision_id)).scalar_one_or_none()
    # A decision that exists but belongs to someone else's vault must look exactly like one
    # that doesn't exist at all -- never leak that a given id is valid for another user.
    if decision is None or decision.vault_id != vault.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="decision not found")
    return _serialize(decision)
