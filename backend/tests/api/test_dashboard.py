from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import BucketBalance, User, Vault

from .conftest import stub_auth_header


def test_dashboard_summary_defaults_missing_buckets_to_zero(client: TestClient, db_session: Session) -> None:
    user = User(privy_id="dash-user", wallet="0xDASH")
    db_session.add(user)
    db_session.flush()
    vault = Vault(
        user_id=user.id,
        vault_addr="0xVAULTDASH",
        income_inbox="0xINCOMEDASH",
        topup_inbox="0xTOPUPDASH",
        payout_addr="0xPAYOUTDASH",
        deployed_tx="0xDEPLOYDASH",
    )
    db_session.add(vault)
    db_session.flush()
    db_session.add(BucketBalance(vault_id=vault.id, bucket="Tax", amount=20_000000, as_of_block=100))
    db_session.commit()

    response = client.get("/v1/dashboard/summary", headers=stub_auth_header("dash-user", "0xDASH"))

    assert response.status_code == 200
    body = response.json()
    assert body["balances"]["Tax"] == 20_000000
    assert body["balances"]["Savings"] == 0
    assert body["total"] == 20_000000
    assert body["as_of_block"] == 100


def test_dashboard_summary_requires_auth(client: TestClient) -> None:
    response = client.get("/v1/dashboard/summary")
    assert response.status_code == 401
