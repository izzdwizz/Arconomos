from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import generate_api_key, hash_api_key
from app.db.models import Integration, IntegrationEvent, User, Vault


def test_integration_event_idempotent_on_tx_hash(client: TestClient, db_session: Session) -> None:

    user = User(privy_id="paywall-owner", wallet="0xOWNER")
    db_session.add(user)
    db_session.flush()
    vault = Vault(
        user_id=user.id,
        vault_addr="0xVAULT",
        income_inbox="0xINCOME",
        topup_inbox="0xTOPUP",
        payout_addr="0xPAYOUT",
        deployed_tx="0xDEPLOYTX",
    )
    db_session.add(vault)
    db_session.flush()

    raw_key, key_hash = generate_api_key()
    integration = Integration(vault_id=vault.id, name="paywall", key_hash=key_hash)
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)

    assert hash_api_key(raw_key) == key_hash

    payload = {"tx_hash": "0xabc123", "label": "AI answer", "amount": 5000, "cost": 200}
    headers = {"X-API-Key": raw_key}

    first = client.post(f"/v1/integrations/{integration.id}/events", json=payload, headers=headers)
    assert first.status_code == 201
    assert first.json()["deduplicated"] is False

    second = client.post(f"/v1/integrations/{integration.id}/events", json=payload, headers=headers)
    assert second.status_code == 201
    assert second.json()["deduplicated"] is True
    assert second.json()["id"] == first.json()["id"]

    count = db_session.execute(
        select(func.count()).select_from(IntegrationEvent).where(IntegrationEvent.tx_hash == "0xabc123")
    ).scalar_one()
    assert count == 1


def test_integration_event_requires_valid_api_key(client: TestClient, db_session: Session) -> None:
    user = User(privy_id="paywall-owner-2", wallet="0xOWNER2")
    db_session.add(user)
    db_session.flush()
    vault = Vault(
        user_id=user.id,
        vault_addr="0xVAULT2",
        income_inbox="0xINCOME2",
        topup_inbox="0xTOPUP2",
        payout_addr="0xPAYOUT2",
        deployed_tx="0xDEPLOYTX2",
    )
    db_session.add(vault)
    db_session.flush()
    _, key_hash = generate_api_key()
    integration = Integration(vault_id=vault.id, name="paywall", key_hash=key_hash)
    db_session.add(integration)
    db_session.commit()
    db_session.refresh(integration)

    payload = {"tx_hash": "0xdef456", "label": "AI answer", "amount": 5000}

    no_key = client.post(f"/v1/integrations/{integration.id}/events", json=payload)
    assert no_key.status_code == 401

    wrong_key = client.post(
        f"/v1/integrations/{integration.id}/events", json=payload, headers={"X-API-Key": "wrong-key"}
    )
    assert wrong_key.status_code == 401
