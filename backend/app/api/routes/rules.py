"""PUT /v1/rules: the default kind for anything sent straight to the vault, plus known-
source rules (sender -> income/transfer). Classification precedence at deposit time is
known-source, then default -- see app/indexer/classify.py, which this data feeds."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Rules, Vault
from app.db.session import get_db

from ..deps import get_current_vault

router = APIRouter(tags=["rules"])


class KnownSourceIn(BaseModel):
    sender: str
    kind: Literal["income", "transfer"]
    label: str


class RulesIn(BaseModel):
    default_kind: Literal["income", "transfer"]
    known_sources: list[KnownSourceIn] = []


def _serialize(rules: Rules) -> dict[str, Any]:
    return {"vault_id": rules.vault_id, "default_kind": rules.default_kind, "known_sources": rules.known_sources}


@router.get("/v1/rules")
def get_rules(vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)) -> dict[str, Any]:
    rules = db.execute(select(Rules).where(Rules.vault_id == vault.id)).scalar_one_or_none()
    if rules is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rules not set for this vault")
    return _serialize(rules)


@router.put("/v1/rules")
def put_rules(
    body: RulesIn, vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)
) -> dict[str, Any]:
    rules = db.execute(select(Rules).where(Rules.vault_id == vault.id)).scalar_one_or_none()
    known_sources = [ks.model_dump() for ks in body.known_sources]
    if rules is None:
        rules = Rules(vault_id=vault.id, default_kind=body.default_kind, known_sources=known_sources)
        db.add(rules)
    else:
        rules.default_kind = body.default_kind
        rules.known_sources = known_sources
    db.commit()
    db.refresh(rules)
    return _serialize(rules)
