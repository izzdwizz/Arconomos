"""Tax defaults and the user's confirmed rate (PRD setup step 4). Defaults are looked up
by country + income type; this table starts empty and is filled in by research per
country as sellers onboard (PRD open question: "which countries are the first sellers
in?") rather than seeded with rates this session can't stand behind as current -- a
missing default just means the wizard asks the user to enter their own rate manually.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TaxDefault, TaxSettings, Vault
from app.db.session import get_db

from ..deps import get_current_vault

router = APIRouter(tags=["tax"])


class TaxSettingsIn(BaseModel):
    rate_bps: int
    delay_hours: int = 72


@router.get("/v1/tax-defaults")
def get_tax_default(
    country: str = Query(...), income_type: str = Query(...), db: Session = Depends(get_db)
) -> dict[str, Any]:
    row = db.execute(
        select(TaxDefault).where(TaxDefault.country == country, TaxDefault.income_type == income_type)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no default set-aside rate for this country/income type yet -- enter one manually",
        )
    return {
        "country": row.country,
        "income_type": row.income_type,
        "rate_bps": row.rate_bps,
        "source_url": row.source_url,
        "retrieved_at": row.retrieved_at.isoformat(),
    }


@router.get("/v1/tax")
def get_tax_settings(vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.execute(select(TaxSettings).where(TaxSettings.vault_id == vault.id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tax settings not set for this vault")
    return {"vault_id": row.vault_id, "rate_bps": row.rate_bps, "delay_hours": row.delay_hours}


@router.put("/v1/tax")
def put_tax_settings(
    body: TaxSettingsIn, vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Updates the cached confirmed rate. The on-chain tax floor (`minTaxBps`) is set once
    at vault deploy time and isn't changed by this call -- editing it later needs a
    separate owner-signed guardrail change, same as any other guardrail."""
    row = db.execute(select(TaxSettings).where(TaxSettings.vault_id == vault.id)).scalar_one_or_none()
    if row is None:
        row = TaxSettings(vault_id=vault.id, rate_bps=body.rate_bps, delay_hours=body.delay_hours)
        db.add(row)
    else:
        row.rate_bps = body.rate_bps
        row.delay_hours = body.delay_hours
    db.commit()
    db.refresh(row)
    return {"vault_id": row.vault_id, "rate_bps": row.rate_bps, "delay_hours": row.delay_hours}
