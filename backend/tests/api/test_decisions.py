from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Decision, User, Vault

from .conftest import stub_auth_header


def _make_user_with_vault_and_decision(db_session: Session, *, privy_id: str, wallet: str) -> tuple[User, Decision]:
    user = User(privy_id=privy_id, wallet=wallet)
    db_session.add(user)
    db_session.flush()

    vault = Vault(
        user_id=user.id,
        vault_addr=f"0xVAULT_{privy_id}",
        income_inbox=f"0xINCOME_{privy_id}",
        topup_inbox=f"0xTOPUP_{privy_id}",
        payout_addr=f"0xPAYOUT_{privy_id}",
        deployed_tx=f"0xDEPLOYTX_{privy_id}",
    )
    db_session.add(vault)
    db_session.flush()

    decision = Decision(
        vault_id=vault.id,
        prev_hash="0" * 64,
        hash=f"hash-{privy_id}",
        trigger="deposit",
        snapshot={},
        proposed=[],
        policy_result={"accepted": True},
        reason="income deposit allocated by current split",
    )
    db_session.add(decision)
    db_session.commit()
    db_session.refresh(decision)
    return user, decision


def test_user_cannot_read_other_vault(client: TestClient, db_session: Session) -> None:
    _, alice_decision = _make_user_with_vault_and_decision(db_session, privy_id="alice", wallet="0xALICE")
    _, bob_decision = _make_user_with_vault_and_decision(db_session, privy_id="bob", wallet="0xBOB")

    alice_headers = stub_auth_header("alice", "0xALICE")

    own_response = client.get(f"/v1/decisions/{alice_decision.id}", headers=alice_headers)
    assert own_response.status_code == 200

    cross_response = client.get(f"/v1/decisions/{bob_decision.id}", headers=alice_headers)
    assert cross_response.status_code == 404

    nonexistent_response = client.get("/v1/decisions/does-not-exist", headers=alice_headers)
    assert nonexistent_response.status_code == 404
    # A real decision belonging to someone else must look exactly like a nonexistent one.
    assert cross_response.json() == nonexistent_response.json()


def test_list_decisions_only_returns_own_vault(client: TestClient, db_session: Session) -> None:
    _make_user_with_vault_and_decision(db_session, privy_id="alice2", wallet="0xALICE2")
    _make_user_with_vault_and_decision(db_session, privy_id="bob2", wallet="0xBOB2")

    response = client.get("/v1/decisions", headers=stub_auth_header("alice2", "0xALICE2"))

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["hash"] == "hash-alice2"
