"""The deterministic check between the model's proposed actions and the chain.

Mirrors the contract's own guardrails plus stricter off-chain ones, so a bad proposal is
dropped and logged here rather than reverting on-chain (or worse, silently doing nothing
useful with the gas it spent). See PRD "One cycle" step 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    ALLOCATE = "allocate"
    ADJUST_SPLIT = "adjust_split"
    REBALANCE = "rebalance"
    SWEEP_TO_YIELD = "sweep_to_yield"
    REDEEM = "redeem"
    PAY_OWNER = "pay_owner"
    FLAG = "flag"


@dataclass(frozen=True)
class ProposedAction:
    type: ActionType
    params: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class PolicyResult:
    accepted: bool
    rejected_rule: str | None = None


BUCKET_TAX = "Tax"


def check_action(action: ProposedAction, guardrails: dict[str, Any], state: dict[str, Any]) -> PolicyResult:
    """`guardrails` mirrors the vault's own: max_split_change_bps_per_week, min_tax_bps,
    buffer_floor, owner_pay_cap_per_period. `state` carries current bucket balances,
    split_bps, and anything else the checks below need.
    """
    if action.type == ActionType.ADJUST_SPLIT:
        return _check_adjust_split(action, guardrails, state)
    if action.type == ActionType.REBALANCE:
        return _check_rebalance(action, state)
    if action.type == ActionType.REDEEM:
        return _check_redeem(action, state)
    if action.type == ActionType.PAY_OWNER:
        return _check_pay_owner(action, guardrails, state)
    if action.type == ActionType.SWEEP_TO_YIELD:
        return _check_sweep_to_yield(action, state)
    if action.type in (ActionType.ALLOCATE, ActionType.FLAG):
        return PolicyResult(accepted=True)
    return PolicyResult(accepted=False, rejected_rule="unknown_action_type")


def _check_adjust_split(action: ProposedAction, guardrails: dict[str, Any], state: dict[str, Any]) -> PolicyResult:
    new_bps: dict[str, int] = action.params["new_bps"]
    old_bps: dict[str, int] = state["split_bps"]

    if sum(new_bps.values()) != 10_000:
        return PolicyResult(accepted=False, rejected_rule="split_must_sum_to_10000")

    if new_bps.get(BUCKET_TAX, 0) < guardrails["min_tax_bps"]:
        return PolicyResult(accepted=False, rejected_rule="below_tax_floor")

    max_change = guardrails["max_split_change_bps_per_week"]
    cumulative_change = state.get("guardrail_cumulative_change", {})
    for bucket, new_value in new_bps.items():
        old_value = old_bps.get(bucket, 0)
        already_used = cumulative_change.get(bucket, 0)
        if already_used + abs(new_value - old_value) > max_change:
            return PolicyResult(accepted=False, rejected_rule="exceeds_weekly_guardrail")

    return PolicyResult(accepted=True)


def _check_rebalance(action: ProposedAction, state: dict[str, Any]) -> PolicyResult:
    if action.params["from_bucket"] == BUCKET_TAX:
        return PolicyResult(accepted=False, rejected_rule="cannot_draw_down_tax")

    balances = state["bucket_balances"]
    if action.params["amount"] > balances.get(action.params["from_bucket"], 0):
        return PolicyResult(accepted=False, rejected_rule="insufficient_bucket_balance")

    return PolicyResult(accepted=True)


def _check_sweep_to_yield(action: ProposedAction, state: dict[str, Any]) -> PolicyResult:
    balances = state["bucket_balances"]
    if action.params["amount"] > balances.get(action.params["bucket"], 0):
        return PolicyResult(accepted=False, rejected_rule="insufficient_bucket_balance")
    min_amount = state.get("min_yield_move_amount", 0)
    if action.params["amount"] < min_amount:
        return PolicyResult(accepted=False, rejected_rule="below_minimum_yield_move")
    return PolicyResult(accepted=True)


def _check_redeem(action: ProposedAction, state: dict[str, Any]) -> PolicyResult:
    """A redeem must not pull out more than what's actually needed plus a margin."""
    needed = state.get("amount_needed", 0)
    margin = state.get("redeem_margin", 0)
    if action.params["amount"] > needed + margin:
        return PolicyResult(accepted=False, rejected_rule="redeem_exceeds_needed_plus_margin")
    return PolicyResult(accepted=True)


def _check_pay_owner(action: ProposedAction, guardrails: dict[str, Any], state: dict[str, Any]) -> PolicyResult:
    amount = action.params["amount"]
    if amount > guardrails["owner_pay_cap_per_period"]:
        return PolicyResult(accepted=False, rejected_rule="exceeds_pay_cap")

    buffer_balance = state["bucket_balances"].get("Buffer", 0)
    buffer_floor = guardrails["buffer_floor"]
    if buffer_balance - amount < buffer_floor:
        return PolicyResult(accepted=False, rejected_rule="breaches_buffer_floor")

    return PolicyResult(accepted=True)
