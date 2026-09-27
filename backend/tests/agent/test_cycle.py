from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.cycle import run_cycle
from app.agent.model_client import ScriptedModelClient
from app.db.models import Base, Bill, BucketBalance, Decision, User, Vault


class FakeChainClient:
    """Stands in for app.chain.client.ChainClient: no network, fixed guardrails/split."""

    def __init__(self, guardrails: dict[str, int], split_bps: list[int]) -> None:
        self._guardrails = guardrails
        self._split_bps = split_bps

    def get_guardrails(self, vault_address: str) -> dict[str, int]:
        return dict(self._guardrails)

    def get_split_bps(self, vault_address: str) -> list[int]:
        return list(self._split_bps)


class FakeSigner:
    address = "0xOPERATOR"


def _make_db_and_vault():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    user = User(privy_id="cycle-user", wallet="0xCYCLE")
    db.add(user)
    db.flush()
    vault = Vault(
        user_id=user.id,
        vault_addr="0xVAULTCYCLE",
        income_inbox="0xINCOMECYCLE",
        topup_inbox="0xTOPUPCYCLE",
        payout_addr="0xPAYOUTCYCLE",
        deployed_tx="0xDEPLOYCYCLE",
    )
    db.add(vault)
    db.commit()
    return db, vault


def _guardrails() -> dict[str, int]:
    return {
        "min_tax_bps": 2000,
        "max_split_change_bps_per_week": 1000,
        "owner_pay_cap_per_period": 500_000000,
        "buffer_floor": 100_000000,
    }


def test_cycle_flags_underfunded_bill_without_touching_chain() -> None:
    db, vault = _make_db_and_vault()
    db.add(BucketBalance(vault_id=vault.id, bucket="Bills", amount=10_000000, as_of_block=1))
    db.add(
        Bill(
            vault_id=vault.id,
            name="Rent",
            amount=100_000000,
            due_date=datetime.now(UTC) + timedelta(days=5),
        )
    )
    db.commit()

    chain = FakeChainClient(_guardrails(), [2000, 2000, 2000, 1500, 1500, 1000])
    executed = []

    def fake_execute(client, signer, vault_address, action):
        executed.append(action)
        return "0xshouldnothappen"

    result = run_cycle(db, chain, FakeSigner(), vault, trigger="daily", model_client=ScriptedModelClient(), execute_action_fn=fake_execute)

    assert result.accepted_count == 1  # the flag itself is "accepted" by policy (flags always are)
    assert executed == []  # but flags never reach the chain
    assert result.tx_hashes == []

    decision = db.execute(select(Decision).where(Decision.id == result.decision_id)).scalar_one()
    assert "Rent" in decision.reason
    assert decision.prev_hash == "0" * 64


def test_cycle_chains_decisions_by_hash() -> None:
    db, vault = _make_db_and_vault()
    chain = FakeChainClient(_guardrails(), [2000, 2000, 2000, 1500, 1500, 1000])

    first = run_cycle(db, chain, FakeSigner(), vault, trigger="daily", model_client=ScriptedModelClient(), execute_action_fn=lambda *a: "0x1")
    second = run_cycle(db, chain, FakeSigner(), vault, trigger="daily", model_client=ScriptedModelClient(), execute_action_fn=lambda *a: "0x2")

    first_decision = db.execute(select(Decision).where(Decision.id == first.decision_id)).scalar_one()
    second_decision = db.execute(select(Decision).where(Decision.id == second.decision_id)).scalar_one()

    assert second_decision.prev_hash == first_decision.hash


def test_cycle_sweeps_idle_buffer_to_yield_and_executes_on_chain() -> None:
    db, vault = _make_db_and_vault()
    db.add(BucketBalance(vault_id=vault.id, bucket="Buffer", amount=1000_000000, as_of_block=1))
    db.commit()

    chain = FakeChainClient(_guardrails(), [2000, 2000, 2000, 1500, 1500, 1000])
    executed = []

    def fake_execute(client, signer, vault_address, action):
        executed.append((vault_address, action.type.value, action.params))
        return "0xdeadbeef"

    result = run_cycle(db, chain, FakeSigner(), vault, trigger="daily", model_client=ScriptedModelClient(), execute_action_fn=fake_execute)

    assert result.tx_hashes == ["0xdeadbeef"]
    assert len(executed) == 1
    assert executed[0][0] == "0xVAULTCYCLE"
    assert executed[0][1] == "sweep_to_yield"

    decision = db.execute(select(Decision).where(Decision.id == result.decision_id)).scalar_one()
    assert decision.tx_hash == "0xdeadbeef"
