from app.agent.policy import ActionType, ProposedAction, check_action


def _guardrails(**overrides):
    base = {
        "min_tax_bps": 2000,
        "max_split_change_bps_per_week": 1000,
        "owner_pay_cap_per_period": 500_0000,
        "buffer_floor": 100_0000,
    }
    base.update(overrides)
    return base


def test_rejects_split_change_over_cap():
    action = ProposedAction(
        type=ActionType.ADJUST_SPLIT,
        params={"new_bps": {"Tax": 2000, "Bills": 3001, "Buffer": 4999}},
        reason="rent is due soon",
    )
    state = {"split_bps": {"Tax": 2000, "Bills": 2000, "Buffer": 6000}, "guardrail_cumulative_change": {}}

    result = check_action(action, _guardrails(), state)

    assert not result.accepted
    assert result.rejected_rule == "exceeds_weekly_guardrail"


def test_accepts_split_change_within_cap():
    action = ProposedAction(
        type=ActionType.ADJUST_SPLIT,
        params={"new_bps": {"Tax": 2000, "Bills": 2500, "Buffer": 5500}},
        reason="rent is due soon",
    )
    state = {"split_bps": {"Tax": 2000, "Bills": 2000, "Buffer": 6000}, "guardrail_cumulative_change": {}}

    result = check_action(action, _guardrails(), state)

    assert result.accepted


def test_rejects_split_change_below_tax_floor():
    action = ProposedAction(
        type=ActionType.ADJUST_SPLIT,
        params={"new_bps": {"Tax": 1000, "Bills": 2000, "Buffer": 7000}},
        reason="reallocate",
    )
    state = {"split_bps": {"Tax": 2000, "Bills": 2000, "Buffer": 6000}, "guardrail_cumulative_change": {}}

    result = check_action(action, _guardrails(), state)

    assert not result.accepted
    assert result.rejected_rule == "below_tax_floor"


def test_rejects_redeem_more_than_needed():
    action = ProposedAction(
        type=ActionType.REDEEM, params={"bucket": "Bills", "amount": 500_0000}, reason="bill due in 2 days"
    )
    state = {"amount_needed": 200_0000, "redeem_margin": 50_0000}

    result = check_action(action, _guardrails(), state)

    assert not result.accepted
    assert result.rejected_rule == "redeem_exceeds_needed_plus_margin"


def test_accepts_redeem_within_needed_plus_margin():
    action = ProposedAction(
        type=ActionType.REDEEM, params={"bucket": "Bills", "amount": 240_0000}, reason="bill due in 2 days"
    )
    state = {"amount_needed": 200_0000, "redeem_margin": 50_0000}

    result = check_action(action, _guardrails(), state)

    assert result.accepted


def test_pay_owner_respects_buffer_floor():
    action = ProposedAction(type=ActionType.PAY_OWNER, params={"amount": 400_0000}, reason="scheduled pay")
    state = {"bucket_balances": {"Buffer": 420_0000}}

    result = check_action(action, _guardrails(buffer_floor=100_0000), state)

    assert not result.accepted
    assert result.rejected_rule == "breaches_buffer_floor"


def test_pay_owner_within_buffer_floor_accepted():
    action = ProposedAction(type=ActionType.PAY_OWNER, params={"amount": 400_0000}, reason="scheduled pay")
    state = {"bucket_balances": {"Buffer": 1050_0000}}

    result = check_action(action, _guardrails(buffer_floor=100_0000), state)

    assert result.accepted


def test_rebalance_out_of_tax_rejected():
    action = ProposedAction(
        type=ActionType.REBALANCE,
        params={"from_bucket": "Tax", "to_bucket": "Bills", "amount": 100_0000},
        reason="cover bill",
    )
    state = {"bucket_balances": {"Tax": 500_0000}}

    result = check_action(action, _guardrails(), state)

    assert not result.accepted
    assert result.rejected_rule == "cannot_draw_down_tax"


def test_unknown_action_type_rejected():
    class FakeAction:
        type: str = "not_a_real_action"
        params: dict = {}  # noqa: RUF012 - simple test double, never mutated
        reason: str = "malformed"

    result = check_action(FakeAction(), _guardrails(), {})  # type: ignore[arg-type]

    assert not result.accepted
    assert result.rejected_rule == "unknown_action_type"
