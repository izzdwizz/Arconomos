from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import User, Vault

from .conftest import stub_auth_header


def _make_vault(db_session: Session, *, privy_id: str) -> None:
    user = User(privy_id=privy_id, wallet=f"0x{privy_id}")
    db_session.add(user)
    db_session.flush()
    vault = Vault(
        user_id=user.id,
        vault_addr=f"0xVAULT_{privy_id}",
        income_inbox=f"0xINCOME_{privy_id}",
        topup_inbox=f"0xTOPUP_{privy_id}",
        payout_addr=f"0xPAYOUT_{privy_id}",
        deployed_tx=f"0xDEPLOY_{privy_id}",
    )
    db_session.add(vault)
    db_session.commit()


def test_bill_crud_roundtrip(client: TestClient, db_session: Session) -> None:
    _make_vault(db_session, privy_id="bills1")
    headers = stub_auth_header("bills1", "0xbills1")

    create = client.post(
        "/v1/bills",
        json={"name": "Rent", "amount": 100_000000, "due_date": "2026-11-01T00:00:00Z", "priority": 1},
        headers=headers,
    )
    assert create.status_code == 201
    bill_id = create.json()["id"]

    listed = client.get("/v1/bills", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["name"] == "Rent"

    patched = client.patch(f"/v1/bills/{bill_id}", json={"amount": 120_000000}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["amount"] == 120_000000
    assert patched.json()["name"] == "Rent"  # untouched fields survive a partial patch

    deleted = client.delete(f"/v1/bills/{bill_id}", headers=headers)
    assert deleted.status_code == 204

    listed_after = client.get("/v1/bills", headers=headers)
    assert listed_after.json() == []


def test_bill_isolated_per_vault(client: TestClient, db_session: Session) -> None:
    _make_vault(db_session, privy_id="billsA")
    _make_vault(db_session, privy_id="billsB")

    create = client.post(
        "/v1/bills",
        json={"name": "Insurance", "amount": 50_000000, "due_date": "2026-12-01T00:00:00Z"},
        headers=stub_auth_header("billsA", "0xbillsA"),
    )
    bill_id = create.json()["id"]

    cross_patch = client.patch(
        f"/v1/bills/{bill_id}", json={"amount": 1}, headers=stub_auth_header("billsB", "0xbillsB")
    )
    assert cross_patch.status_code == 404

    cross_delete = client.delete(f"/v1/bills/{bill_id}", headers=stub_auth_header("billsB", "0xbillsB"))
    assert cross_delete.status_code == 404


def test_goal_crud_roundtrip(client: TestClient, db_session: Session) -> None:
    _make_vault(db_session, privy_id="goals1")
    headers = stub_auth_header("goals1", "0xgoals1")

    create = client.post(
        "/v1/goals",
        json={"name": "New laptop", "target_amount": 2_000_000000, "target_date": "2027-01-01T00:00:00Z"},
        headers=headers,
    )
    assert create.status_code == 201
    goal_id = create.json()["id"]

    patched = client.patch(f"/v1/goals/{goal_id}", json={"priority": 5}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["priority"] == 5
    assert patched.json()["target_amount"] == 2_000_000000

    deleted = client.delete(f"/v1/goals/{goal_id}", headers=headers)
    assert deleted.status_code == 204
