from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bill, Vault
from app.db.session import get_db

from ..deps import get_current_vault

router = APIRouter(tags=["bills"])


class BillIn(BaseModel):
    name: str
    amount: int
    due_date: datetime
    recurrence: str | None = None
    priority: int = 0


class BillPatch(BaseModel):
    name: str | None = None
    amount: int | None = None
    due_date: datetime | None = None
    recurrence: str | None = None
    priority: int | None = None


def _serialize(bill: Bill) -> dict[str, Any]:
    return {
        "id": bill.id,
        "name": bill.name,
        "amount": bill.amount,
        "due_date": bill.due_date.isoformat(),
        "recurrence": bill.recurrence,
        "priority": bill.priority,
    }


def _get_owned_bill(db: Session, vault: Vault, bill_id: str) -> Bill:
    bill = db.execute(select(Bill).where(Bill.id == bill_id)).scalar_one_or_none()
    if bill is None or bill.vault_id != vault.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bill not found")
    return bill


@router.get("/v1/bills")
def list_bills(vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(select(Bill).where(Bill.vault_id == vault.id).order_by(Bill.due_date)).scalars().all()
    return [_serialize(row) for row in rows]


@router.post("/v1/bills", status_code=status.HTTP_201_CREATED)
def create_bill(
    body: BillIn, vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)
) -> dict[str, Any]:
    bill = Bill(
        vault_id=vault.id,
        name=body.name,
        amount=body.amount,
        due_date=body.due_date,
        recurrence=body.recurrence,
        priority=body.priority,
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return _serialize(bill)


@router.patch("/v1/bills/{bill_id}")
def update_bill(
    bill_id: str,
    body: BillPatch,
    vault: Vault = Depends(get_current_vault),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    bill = _get_owned_bill(db, vault, bill_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(bill, field, value)
    db.commit()
    db.refresh(bill)
    return _serialize(bill)


@router.delete("/v1/bills/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bill(bill_id: str, vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)) -> None:
    bill = _get_owned_bill(db, vault, bill_id)
    db.delete(bill)
    db.commit()
