from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.snapshot import build_snapshot
from app.db.models import Base, Bill, BucketBalance, Deposit, Goal, User, Vault


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _make_vault(db: Session) -> Vault:
    user = User(privy_id="snap-user", wallet="0xSNAP")
    db.add(user)
    db.flush()
    vault = Vault(
        user_id=user.id,
        vault_addr="0xVAULTSNAP",
        income_inbox="0xINCOMESNAP",
        topup_inbox="0xTOPUPSNAP",
        payout_addr="0xPAYOUTSNAP",
        deployed_tx="0xDEPLOYSNAP",
    )
    db.add(vault)
    db.flush()
    return vault


def test_snapshot_defaults_missing_buckets_to_zero() -> None:
    db = _make_session()
    vault = _make_vault(db)
    db.add(BucketBalance(vault_id=vault.id, bucket="Tax", amount=100, as_of_block=1))
    db.commit()

    snapshot = build_snapshot(db, vault)

    assert snapshot.bucket_balances["Tax"] == 100
    assert snapshot.bucket_balances["Savings"] == 0


def test_snapshot_includes_bills_due_within_horizon_only() -> None:
    db = _make_session()
    vault = _make_vault(db)
    now = datetime.now(UTC)
    db.add(Bill(vault_id=vault.id, name="Rent", amount=100_000000, due_date=now + timedelta(days=5)))
    db.add(Bill(vault_id=vault.id, name="Insurance", amount=50_000000, due_date=now + timedelta(days=90)))
    db.commit()

    snapshot = build_snapshot(db, vault, bills_horizon_days=20)

    names = {bill["name"] for bill in snapshot.bills_due_soon}
    assert names == {"Rent"}


def test_snapshot_includes_all_goals() -> None:
    db = _make_session()
    vault = _make_vault(db)
    db.add(
        Goal(
            vault_id=vault.id,
            name="Equipment",
            target_amount=5_000_000000,
            target_date=datetime.now(UTC) + timedelta(days=180),
            priority=1,
        )
    )
    db.commit()

    snapshot = build_snapshot(db, vault)

    assert len(snapshot.goals) == 1
    assert snapshot.goals[0]["name"] == "Equipment"


def test_snapshot_buckets_income_deposits_by_week() -> None:
    db = _make_session()
    vault = _make_vault(db)
    now = datetime.now(UTC)

    recent = Deposit(
        vault_id=vault.id,
        tx_hash="0xa",
        log_index=0,
        sender="0xsender",
        amount=1000_000000,
        kind="income",
        kind_source="inbox",
        block_number=1,
    )
    older = Deposit(
        vault_id=vault.id,
        tx_hash="0xb",
        log_index=0,
        sender="0xsender",
        amount=500_000000,
        kind="income",
        kind_source="inbox",
        block_number=2,
    )
    db.add_all([recent, older])
    db.flush()
    # created_at has a server default; overwrite explicitly to control week placement.
    recent.created_at = now - timedelta(days=1)
    older.created_at = now - timedelta(weeks=3)
    db.commit()

    snapshot = build_snapshot(db, vault, income_weeks=4)

    assert sum(snapshot.weekly_income_history) == 1500_000000
    assert snapshot.weekly_income_history[-1] == 1000_000000


def test_snapshot_excludes_transfer_deposits_from_income_history() -> None:
    db = _make_session()
    vault = _make_vault(db)
    db.add(
        Deposit(
            vault_id=vault.id,
            tx_hash="0xc",
            log_index=0,
            sender="0xsender",
            amount=999_000000,
            kind="transfer",
            kind_source="inbox",
            block_number=3,
        )
    )
    db.commit()

    snapshot = build_snapshot(db, vault)

    assert sum(snapshot.weekly_income_history) == 0
