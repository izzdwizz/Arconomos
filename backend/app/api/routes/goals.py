from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Goal, Vault
from app.db.session import get_db

from ..deps import get_current_vault

router = APIRouter(tags=["goals"])


class GoalIn(BaseModel):
    name: str
    target_amount: int
    target_date: datetime
    priority: int = 0


class GoalPatch(BaseModel):
    name: str | None = None
    target_amount: int | None = None
    target_date: datetime | None = None
    priority: int | None = None


def _serialize(goal: Goal) -> dict[str, Any]:
    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": goal.target_amount,
        "target_date": goal.target_date.isoformat(),
        "priority": goal.priority,
    }


def _get_owned_goal(db: Session, vault: Vault, goal_id: str) -> Goal:
    goal = db.execute(select(Goal).where(Goal.id == goal_id)).scalar_one_or_none()
    if goal is None or goal.vault_id != vault.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="goal not found")
    return goal


@router.get("/v1/goals")
def list_goals(vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(select(Goal).where(Goal.vault_id == vault.id).order_by(Goal.target_date)).scalars().all()
    return [_serialize(row) for row in rows]


@router.post("/v1/goals", status_code=status.HTTP_201_CREATED)
def create_goal(
    body: GoalIn, vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)
) -> dict[str, Any]:
    goal = Goal(
        vault_id=vault.id,
        name=body.name,
        target_amount=body.target_amount,
        target_date=body.target_date,
        priority=body.priority,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _serialize(goal)


@router.patch("/v1/goals/{goal_id}")
def update_goal(
    goal_id: str,
    body: GoalPatch,
    vault: Vault = Depends(get_current_vault),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    goal = _get_owned_goal(db, vault, goal_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return _serialize(goal)


@router.delete("/v1/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: str, vault: Vault = Depends(get_current_vault), db: Session = Depends(get_db)) -> None:
    goal = _get_owned_goal(db, vault, goal_id)
    db.delete(goal)
    db.commit()
