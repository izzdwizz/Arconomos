"""Businesses that integrate (the paywall first) authenticate with an API key scoped to
one vault. `POST .../events` is idempotent on tx_hash: the paywall's background reporting
task may retry on failure, and a duplicate report must never double-count revenue.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Integration, IntegrationEvent, Vault
from app.db.session import get_db

from ..deps import generate_api_key, get_current_vault, get_integration_for_request

router = APIRouter(tags=["integrations"])


class CreateIntegrationRequest(BaseModel):
    name: str


@router.post("/v1/integrations", status_code=status.HTTP_201_CREATED)
def create_integration(
    body: CreateIntegrationRequest,
    vault: Vault = Depends(get_current_vault),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    raw_key, key_hash = generate_api_key()
    integration = Integration(vault_id=vault.id, name=body.name, key_hash=key_hash)
    db.add(integration)
    db.commit()
    db.refresh(integration)
    # The raw key is only ever shown here, at creation time; only its hash is stored.
    return {"id": integration.id, "name": integration.name, "api_key": raw_key}


class ReportEventRequest(BaseModel):
    tx_hash: str
    label: str
    amount: int
    cost: int = 0
    reference: str | None = None


@router.post("/v1/integrations/{integration_id}/events", status_code=status.HTTP_201_CREATED)
def report_event(
    body: ReportEventRequest,
    integration: Integration = Depends(get_integration_for_request),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    existing = db.execute(
        select(IntegrationEvent).where(
            IntegrationEvent.integration_id == integration.id,
            IntegrationEvent.tx_hash == body.tx_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"id": existing.id, "tx_hash": existing.tx_hash, "deduplicated": True}

    event = IntegrationEvent(
        integration_id=integration.id,
        tx_hash=body.tx_hash,
        label=body.label,
        amount=body.amount,
        cost=body.cost,
        reference=body.reference,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with a concurrent retry of the same tx_hash; the other request's
        # row won, so treat this one as the same deduplicated outcome.
        db.rollback()
        existing = db.execute(
            select(IntegrationEvent).where(
                IntegrationEvent.integration_id == integration.id,
                IntegrationEvent.tx_hash == body.tx_hash,
            )
        ).scalar_one()
        return {"id": existing.id, "tx_hash": existing.tx_hash, "deduplicated": True}

    db.refresh(event)
    return {"id": event.id, "tx_hash": event.tx_hash, "deduplicated": False}
