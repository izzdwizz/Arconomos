"""Vault creation is the last step of the setup wizard (PRD "Review and fund"): the
frontend has already walked the user through rules, tax, bills, goals and guardrails, and
submits all of it in one request here. The relayer deploys the vault -- the user signs
nothing and needs no gas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chain.client import ChainClient
from app.chain.deploy import VaultDeployRequest, deploy_vault
from app.chain.signer import OperatorSigner
from app.db.models import Bill, Goal, Rules, TaxSettings, User, Vault
from app.db.session import get_db

from ..auth import get_current_user
from ..chain_deps import (
    get_chain_client,
    get_default_operator_address,
    get_relayer_signer,
    get_vault_factory_address,
    get_yield_pool_address,
)
from ..deps import get_current_vault

router = APIRouter(tags=["vaults"])


class KnownSourceIn(BaseModel):
    sender: str
    kind: Literal["income", "transfer"]
    label: str


class BillIn(BaseModel):
    name: str
    amount: int
    due_date: datetime
    recurrence: str | None = None
    priority: int = 0


class GoalIn(BaseModel):
    name: str
    target_amount: int
    target_date: datetime
    priority: int = 0


class OwnerPayIn(BaseModel):
    """Optional per PRD setup step 7: "by default the money sits in the platform and
    grows" -- omitted or disabled means the contract's owner-pay guardrails are all zero,
    so payOwner() can never move anything until the user turns it on later."""

    enabled: bool = False
    cap_per_period: int = 0
    period_days: int = 7
    buffer_floor: int = 0


class CreateVaultRequest(BaseModel):
    country: str
    income_type: str
    tax_rate_bps: int = Field(ge=0, le=10_000)
    tax_delay_hours: int = 72
    max_split_change_bps_per_week: int = 1000
    default_kind: Literal["income", "transfer"] = "transfer"
    known_sources: list[KnownSourceIn] = []
    bills: list[BillIn] = []
    goals: list[GoalIn] = []
    owner_pay: OwnerPayIn = OwnerPayIn()


@router.get("/v1/vaults/me")
def get_my_vault(vault: Vault = Depends(get_current_vault)) -> dict[str, str]:
    return {
        "id": vault.id,
        "vault_addr": vault.vault_addr,
        "income_inbox": vault.income_inbox,
        "topup_inbox": vault.topup_inbox,
        "payout_addr": vault.payout_addr,
    }


@router.post("/v1/vaults", status_code=status.HTTP_201_CREATED)
def create_vault(
    body: CreateVaultRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    chain_client: ChainClient = Depends(get_chain_client),
    relayer_signer: OperatorSigner = Depends(get_relayer_signer),
    factory_address: str = Depends(get_vault_factory_address),
    yield_pool_address: str = Depends(get_yield_pool_address),
    operator_address: str = Depends(get_default_operator_address),
) -> dict[str, str]:
    existing = db.execute(select(Vault).where(Vault.user_id == user.id)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="a vault already exists for this user")

    deploy_request = VaultDeployRequest(
        user_address=user.wallet,
        operator_address=operator_address,
        payout_address=user.wallet,
        yield_pool_address=yield_pool_address,
        min_tax_bps=body.tax_rate_bps,
        max_split_change_bps_per_week=body.max_split_change_bps_per_week,
        tax_withdraw_delay_seconds=body.tax_delay_hours * 3600,
        owner_pay_cap_per_period=body.owner_pay.cap_per_period if body.owner_pay.enabled else 0,
        owner_pay_period_seconds=body.owner_pay.period_days * 86400 if body.owner_pay.enabled else 0,
        buffer_floor=body.owner_pay.buffer_floor if body.owner_pay.enabled else 0,
    )
    deployed = deploy_vault(chain_client, relayer_signer, factory_address, deploy_request)

    vault = Vault(
        user_id=user.id,
        vault_addr=deployed.vault_address,
        income_inbox=deployed.income_inbox_address,
        topup_inbox=deployed.topup_inbox_address,
        payout_addr=user.wallet,
        deployed_tx=deployed.tx_hash,
    )
    db.add(vault)
    db.flush()

    db.add(
        Rules(
            vault_id=vault.id,
            default_kind=body.default_kind,
            known_sources=[ks.model_dump() for ks in body.known_sources],
        )
    )
    db.add(TaxSettings(vault_id=vault.id, rate_bps=body.tax_rate_bps, delay_hours=body.tax_delay_hours))
    for bill in body.bills:
        db.add(
            Bill(
                vault_id=vault.id,
                name=bill.name,
                amount=bill.amount,
                due_date=bill.due_date,
                recurrence=bill.recurrence,
                priority=bill.priority,
            )
        )
    for goal in body.goals:
        db.add(
            Goal(
                vault_id=vault.id,
                name=goal.name,
                target_amount=goal.target_amount,
                target_date=goal.target_date,
                priority=goal.priority,
            )
        )
    db.commit()

    return {
        "id": vault.id,
        "vault_addr": vault.vault_addr,
        "income_inbox": vault.income_inbox,
        "topup_inbox": vault.topup_inbox,
        "deployed_tx": vault.deployed_tx,
    }
