from app.agent.forecast import Forecast, WeekBand
from app.agent.model_client import ScriptedModelClient
from app.agent.snapshot import Snapshot


def _forecast(needed_per_week: float = 0.0) -> Forecast:
    return Forecast(
        weeks=[
            WeekBand(week=i, income_low=800.0, income_mid=1000.0, income_high=1200.0, needed=needed_per_week)
            for i in range(12)
        ]
    )


def test_flags_bill_when_bills_bucket_is_short() -> None:
    snapshot = Snapshot(
        vault_id="v1",
        bucket_balances={"Bills": 50_000000, "Buffer": 0},
        bills_due_soon=[{"id": "b1", "name": "Rent", "amount": 100_000000, "due_date": "2026-11-01"}],
    )

    actions = ScriptedModelClient().propose_actions(snapshot, _forecast(), guardrails={})

    assert len(actions) == 1
    assert actions[0]["type"] == "flag"
    assert "Rent" in actions[0]["reason"]


def test_no_flag_when_bills_bucket_covers_the_bill() -> None:
    snapshot = Snapshot(
        vault_id="v1",
        bucket_balances={"Bills": 200_000000, "Buffer": 0},
        bills_due_soon=[{"id": "b1", "name": "Rent", "amount": 100_000000, "due_date": "2026-11-01"}],
    )

    actions = ScriptedModelClient().propose_actions(snapshot, _forecast(), guardrails={})

    assert actions == []


def test_sweeps_idle_buffer_margin_to_yield() -> None:
    snapshot = Snapshot(vault_id="v1", bucket_balances={"Buffer": 1000_000000})

    actions = ScriptedModelClient().propose_actions(
        snapshot, _forecast(needed_per_week=100_000000), guardrails={"min_yield_move_amount": 1_000000}
    )

    sweep_actions = [a for a in actions if a["type"] == "sweep_to_yield"]
    assert len(sweep_actions) == 1
    assert sweep_actions[0]["params"]["amount"] == 1000_000000 - 200_000000
    # A float amount here would fail ABI encoding as a uint256 the moment it reaches a
    # real contract call (caught by manually running the RUNBOOK's walkthrough) -- must
    # always be a plain int, since forecast.weeks[].needed is a float.
    assert isinstance(sweep_actions[0]["params"]["amount"], int)


def test_no_sweep_when_below_minimum_move_amount() -> None:
    snapshot = Snapshot(vault_id="v1", bucket_balances={"Buffer": 100_000000})

    actions = ScriptedModelClient().propose_actions(
        snapshot, _forecast(needed_per_week=40_000000), guardrails={"min_yield_move_amount": 50_000000}
    )

    assert not any(a["type"] == "sweep_to_yield" for a in actions)
