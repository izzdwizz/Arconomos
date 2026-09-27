"""Parses the model's tool-call output into typed ProposedActions.

The model is not trusted to emit anything that reaches the chain directly: an unrecognized
action name, or params that don't match the action's shape, is rejected here before it ever
gets near app/agent/policy.py.
"""

from __future__ import annotations

from typing import Any

from app.agent.policy import ActionType, ProposedAction

REQUIRED_PARAMS: dict[ActionType, set[str]] = {
    ActionType.ALLOCATE: set(),
    ActionType.ADJUST_SPLIT: {"new_bps"},
    ActionType.REBALANCE: {"from_bucket", "to_bucket", "amount"},
    ActionType.SWEEP_TO_YIELD: {"bucket", "amount"},
    ActionType.REDEEM: {"bucket", "amount"},
    ActionType.PAY_OWNER: {"amount"},
    ActionType.FLAG: {"message"},
}


class UnknownActionError(ValueError):
    pass


class MalformedActionError(ValueError):
    pass


def parse_model_action(raw: dict[str, Any]) -> ProposedAction:
    """`raw` is one tool call from the model: {"type": ..., "params": {...}, "reason": ...}."""
    raw_type = raw.get("type")
    try:
        action_type = ActionType(raw_type)
    except ValueError as exc:
        raise UnknownActionError(f"model proposed an unrecognized action type: {raw_type!r}") from exc

    params = raw.get("params", {})
    missing = REQUIRED_PARAMS[action_type] - params.keys()
    if missing:
        raise MalformedActionError(f"{action_type.value} is missing required params: {sorted(missing)}")

    reason = raw.get("reason")
    if not reason or not isinstance(reason, str):
        raise MalformedActionError("every proposed action needs a plain-language reason")

    return ProposedAction(type=action_type, params=params, reason=reason)


def parse_model_actions(raw_actions: list[dict[str, Any]]) -> list[ProposedAction]:
    """Any single malformed or unrecognized action invalidates the whole batch: a model that
    hallucinated one tool call is not trusted to have gotten the rest right either."""
    return [parse_model_action(raw) for raw in raw_actions]
