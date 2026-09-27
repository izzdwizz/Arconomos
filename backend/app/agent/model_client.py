"""The model gets the snapshot, forecast and guardrails, and picks from the fixed set of
typed actions (app/agent/policy.py's ActionType) via tool calls. Behind one interface so
the provider is swappable and so scenario tests (PRD: "income drops 60%", "annual insurance
due in 20 days"...) can run against a scripted stub in CI, with the real model only in the
nightly suite.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from app.agent.forecast import Forecast
from app.agent.snapshot import Snapshot

SYSTEM_PROMPT = """You are the planning step of Oikonomos, an AI treasury operator. You are \
given a snapshot of one user's vault, a 12-week income forecast, and the guardrails you \
must respect. Propose zero or more actions from the fixed set: allocate, adjust_split, \
rebalance, sweep_to_yield, redeem, pay_owner, flag. Each action needs a plain-language \
reason. A downstream policy check will reject anything that violates a guardrail, so it is \
safe to propose conservatively -- rejected actions are logged and cost nothing."""


class ModelClient(Protocol):
    def propose_actions(
        self, snapshot: Snapshot, forecast: Forecast, guardrails: dict[str, Any]
    ) -> list[dict[str, Any]]: ...


class ScriptedModelClient:
    """Deterministic stand-in for CI and the scenario suite: a small set of rules that
    mirror what we'd want the real model to propose, without a network call. See PRD
    "Model and evaluation": scenarios run against this in CI, the real model only nightly.
    """

    def propose_actions(
        self, snapshot: Snapshot, forecast: Forecast, guardrails: dict[str, Any]
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []

        for bill in snapshot.bills_due_soon:
            bills_balance = snapshot.bucket_balances.get("Bills", 0)
            if bills_balance < bill["amount"]:
                shortfall = bill["amount"] - bills_balance
                actions.append(
                    {
                        "type": "flag",
                        "params": {"message": f"{bill['name']} is due soon and Bills is short by {shortfall}"},
                        "reason": f"{bill['name']} due {bill['due_date']}, Bills bucket short by {shortfall}",
                    }
                )

        buffer_balance = snapshot.bucket_balances.get("Buffer", 0)
        next_two_weeks_need = sum(w.needed for w in forecast.weeks[:2])
        # forecast.weeks[].needed is a float (statistically derived); on-chain amounts are
        # uint256 base units, so this must be a whole int before it ever reaches a contract
        # call -- truncating (not rounding) means we never propose sweeping fractional
        # margin we don't actually have.
        idle_margin = int(buffer_balance - next_two_weeks_need)
        min_yield_move = guardrails.get("min_yield_move_amount", 0)
        if idle_margin > 0 and idle_margin >= min_yield_move:
            actions.append(
                {
                    "type": "sweep_to_yield",
                    "params": {"bucket": "Buffer", "amount": idle_margin},
                    "reason": "Buffer holds more than the next two weeks need; sweeping the idle margin to yield",
                }
            )

        return actions


class OpenAIModelClient:
    """Real provider, behind the same interface. Uses tool calls so the model can only
    emit one of the fixed action types with well-typed params -- see PRD "Model and
    evaluation": OpenAI, kept behind one interface so it's swappable.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._api_key = api_key
        self._model = model

    def propose_actions(
        self, snapshot: Snapshot, forecast: Forecast, guardrails: dict[str, Any]
    ) -> list[dict[str, Any]]:
        from openai import OpenAI  # deferred: only imported if this client is actually used

        client = OpenAI(api_key=self._api_key)
        user_payload = {
            "snapshot": {
                "bucket_balances": snapshot.bucket_balances,
                "bills_due_soon": snapshot.bills_due_soon,
                "goals": snapshot.goals,
            },
            "forecast_weeks": [
                {
                    "week": w.week,
                    "income_low": w.income_low,
                    "income_mid": w.income_mid,
                    "income_high": w.income_high,
                    "needed": w.needed,
                }
                for w in forecast.weeks
            ],
            "guardrails": guardrails,
        }

        # openai's message/tool TypedDicts are heavier than this thin wrapper needs.
        response = client.chat.completions.create(  # type: ignore[call-overload]
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            tools=[_ACTIONS_TOOL_SCHEMA],
            tool_choice={"type": "function", "function": {"name": "propose_actions"}},
        )

        message = response.choices[0].message
        if not message.tool_calls:
            return []
        arguments = json.loads(message.tool_calls[0].function.arguments)
        actions: list[dict[str, Any]] = arguments.get("actions", [])
        return actions


_ACTIONS_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "propose_actions",
        "description": "Propose zero or more treasury actions for this vault.",
        "parameters": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "allocate",
                                    "adjust_split",
                                    "rebalance",
                                    "sweep_to_yield",
                                    "redeem",
                                    "pay_owner",
                                    "flag",
                                ],
                            },
                            "params": {"type": "object"},
                            "reason": {"type": "string"},
                        },
                        "required": ["type", "params", "reason"],
                    },
                }
            },
            "required": ["actions"],
        },
    },
}
