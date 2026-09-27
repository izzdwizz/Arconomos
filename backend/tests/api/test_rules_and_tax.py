from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import TaxDefault, User, Vault

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


def test_put_rules_creates_then_updates(client: TestClient, db_session: Session) -> None:
    _make_vault(db_session, privy_id="rules1")
    headers = stub_auth_header("rules1", "0xrules1")

    first = client.put(
        "/v1/rules",
        json={"default_kind": "transfer", "known_sources": [{"sender": "0xPAYWALL", "kind": "income", "label": "Paywall"}]},
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json()["default_kind"] == "transfer"
    assert len(first.json()["known_sources"]) == 1

    second = client.put("/v1/rules", json={"default_kind": "income", "known_sources": []}, headers=headers)
    assert second.status_code == 200
    assert second.json()["default_kind"] == "income"
    assert second.json()["known_sources"] == []

    fetched = client.get("/v1/rules", headers=headers)
    assert fetched.json()["default_kind"] == "income"


def test_get_rules_404_before_set(client: TestClient, db_session: Session) -> None:
    _make_vault(db_session, privy_id="rules2")
    response = client.get("/v1/rules", headers=stub_auth_header("rules2", "0xrules2"))
    assert response.status_code == 404


def test_tax_default_lookup_missing_returns_404(client: TestClient) -> None:
    response = client.get("/v1/tax-defaults", params={"country": "XX", "income_type": "freelance"})
    assert response.status_code == 404


def test_tax_default_lookup_found(client: TestClient, db_session: Session) -> None:
    db_session.add(
        TaxDefault(
            country="TESTLAND",
            income_type="freelance",
            rate_bps=2500,
            source_url="https://example.gov/tax",
        )
    )
    db_session.commit()

    response = client.get("/v1/tax-defaults", params={"country": "TESTLAND", "income_type": "freelance"})

    assert response.status_code == 200
    assert response.json()["rate_bps"] == 2500
    assert response.json()["source_url"] == "https://example.gov/tax"


def test_put_tax_settings_roundtrip(client: TestClient, db_session: Session) -> None:
    _make_vault(db_session, privy_id="tax1")
    headers = stub_auth_header("tax1", "0xtax1")

    put_response = client.put("/v1/tax", json={"rate_bps": 2000, "delay_hours": 72}, headers=headers)
    assert put_response.status_code == 200
    assert put_response.json()["rate_bps"] == 2000

    updated = client.put("/v1/tax", json={"rate_bps": 2200, "delay_hours": 48}, headers=headers)
    assert updated.json()["rate_bps"] == 2200
    assert updated.json()["delay_hours"] == 48

    fetched = client.get("/v1/tax", headers=headers)
    assert fetched.json()["rate_bps"] == 2200
