import pytest

from app.agent.planner import (
    MalformedActionError,
    UnknownActionError,
    parse_model_action,
    parse_model_actions,
)
from app.agent.policy import ActionType


def test_model_output_with_unknown_action_is_rejected():
    raw = {"type": "transfer_to_the_moon", "params": {"amount": 100}, "reason": "yolo"}

    with pytest.raises(UnknownActionError):
        parse_model_action(raw)


def test_model_output_missing_required_param_is_rejected():
    raw = {"type": "rebalance", "params": {"from_bucket": "Bills"}, "reason": "short on rent"}

    with pytest.raises(MalformedActionError):
        parse_model_action(raw)


def test_model_output_missing_reason_is_rejected():
    raw = {"type": "pay_owner", "params": {"amount": 100}}

    with pytest.raises(MalformedActionError):
        parse_model_action(raw)


def test_well_formed_action_parses():
    raw = {"type": "pay_owner", "params": {"amount": 100}, "reason": "scheduled pay date"}

    action = parse_model_action(raw)

    assert action.type == ActionType.PAY_OWNER
    assert action.params == {"amount": 100}


def test_one_bad_action_invalidates_the_whole_batch():
    raw_actions = [
        {"type": "pay_owner", "params": {"amount": 100}, "reason": "scheduled pay date"},
        {"type": "not_a_real_action", "params": {}, "reason": "hallucinated"},
    ]

    with pytest.raises(UnknownActionError):
        parse_model_actions(raw_actions)
