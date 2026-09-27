"""One agent cycle (PRD "Agent design > One cycle"): observe, forecast, plan, check, log,
act, explain. Runs on every deposit, daily, weekly, and on an owner action -- the caller
decides `trigger` and how often to call this; the cycle itself is trigger-agnostic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.forecast import forecast_income
from app.agent.model_client import ModelClient
from app.agent.planner import MalformedActionError, UnknownActionError, parse_model_actions
from app.agent.policy import ActionType, PolicyResult, check_action
from app.agent.snapshot import Snapshot, build_snapshot
from app.chain.client import ChainClient, SimulationRevertedError
from app.chain.signer import OperatorSigner
from app.db.models import Decision, Vault

GENESIS_HASH = "0" * 64


class ActionExecutor(Protocol):
    """Narrows app.chain.actions.execute_action to what the cycle needs, so tests can
    substitute a fake without a real chain connection."""

    def __call__(self, client: ChainClient, signer: OperatorSigner, vault_address: str, action: Any) -> str: ...


@dataclass(frozen=True)
class CycleResult:
    decision_id: str
    accepted_count: int
    rejected_count: int
    tx_hashes: list[str]


def _guardrails_for(chain_client: ChainClient, vault: Vault) -> dict[str, Any]:
    guardrails = chain_client.get_guardrails(vault.vault_addr)
    guardrails["min_yield_move_amount"] = 0
    return guardrails


def _decision_hash(prev_hash: str, trigger: str, snapshot: dict[str, Any], proposed: list[Any], reason: str) -> str:
    payload = {"prev_hash": prev_hash, "trigger": trigger, "snapshot": snapshot, "proposed": proposed, "reason": reason}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def run_cycle(
    db: Session,
    chain_client: ChainClient,
    signer: OperatorSigner,
    vault: Vault,
    trigger: str,
    model_client: ModelClient,
    execute_action_fn: ActionExecutor,
) -> CycleResult:
    # Observe
    snapshot: Snapshot = build_snapshot(db, vault)

    # Forecast (code)
    guardrails = _guardrails_for(chain_client, vault)
    # setup_monthly_income (the owner's rough figure from the setup wizard, PRD step 7) has
    # no backing table yet -- the setup wizard and its API aren't built. 0.0 degrades to a
    # zero-width cold-start band rather than crashing; wire this up once that table exists.
    forecast = forecast_income(
        weekly_income_history=snapshot.weekly_income_history,
        setup_monthly_income=0.0,
    )

    # Plan (model)
    raw_actions = model_client.propose_actions(snapshot, forecast, guardrails)
    try:
        proposed_actions = parse_model_actions(raw_actions)
    except (UnknownActionError, MalformedActionError) as exc:
        # The whole batch is untrusted if any one action doesn't fit the fixed set --
        # logged as a fully-rejected cycle rather than silently dropped.
        proposed_actions = []
        raw_actions = [{"error": str(exc), "raw": raw_actions}]

    # Check (code) -- every proposed action against the same guardrails the contract has,
    # plus stricter off-chain ones baked into check_action.
    state = {
        "split_bps": dict(zip(["Tax", "Bills", "Goals", "OwnerPay", "Buffer", "Savings"], chain_client.get_split_bps(vault.vault_addr), strict=True)),
        "bucket_balances": snapshot.bucket_balances,
        "guardrail_cumulative_change": {},
    }

    policy_results: list[PolicyResult] = [check_action(action, guardrails, state) for action in proposed_actions]
    accepted = [(a, r) for a, r in zip(proposed_actions, policy_results, strict=True) if r.accepted]
    rejected = [(a, r) for a, r in zip(proposed_actions, policy_results, strict=True) if not r.accepted]

    reason = "; ".join(a.reason for a, _ in accepted) or "no action needed this cycle"

    # Log (before acting) -- hash-chained to the vault's last decision.
    prev = db.execute(
        select(Decision).where(Decision.vault_id == vault.id).order_by(Decision.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    prev_hash = prev.hash if prev else GENESIS_HASH

    snapshot_dict = {
        "bucket_balances": snapshot.bucket_balances,
        "bills_due_soon": snapshot.bills_due_soon,
        "goals": snapshot.goals,
    }
    proposed_dict = [{"type": a.type.value, "params": a.params, "reason": a.reason} for a in proposed_actions]
    policy_dict = [
        {"accepted": r.accepted, "rejected_rule": r.rejected_rule, "action": a.type.value}
        for a, r in zip(proposed_actions, policy_results, strict=True)
    ]

    entry_hash = _decision_hash(prev_hash, trigger, snapshot_dict, proposed_dict, reason)
    decision = Decision(
        vault_id=vault.id,
        prev_hash=prev_hash,
        hash=entry_hash,
        trigger=trigger,
        snapshot=snapshot_dict,
        proposed=proposed_dict,
        policy_result={"accepted": policy_dict, "raw_model_output": raw_actions if not proposed_actions else None},
        reason=reason,
    )
    db.add(decision)
    db.flush()

    # Act -- only the accepted actions ever reach the chain.
    tx_hashes: list[str] = []
    for action, _result in accepted:
        if action.type == ActionType.FLAG:
            continue  # flags need the owner; no money moves
        try:
            tx_hash = execute_action_fn(chain_client, signer, vault.vault_addr, action)
            tx_hashes.append(tx_hash)
        except SimulationRevertedError:
            # The contract's own guardrails disagreed with our off-chain check; treat as
            # rejected rather than crash the cycle. A real mismatch here is a bug worth
            # alerting on, but it must never take down the scheduler.
            rejected.append((action, PolicyResult(accepted=False, rejected_rule="simulation_reverted")))

    if tx_hashes:
        decision.tx_hash = tx_hashes[0]
    db.commit()

    return CycleResult(
        decision_id=decision.id,
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        tx_hashes=tx_hashes,
    )
