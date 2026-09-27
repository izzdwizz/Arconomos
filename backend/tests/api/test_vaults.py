from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.chain_deps import (
    get_chain_client,
    get_default_operator_address,
    get_relayer_signer,
    get_vault_factory_address,
    get_yield_pool_address,
)
from app.api.main import app
from app.chain.deploy import DeployedVault
from app.db.models import Bill, Goal, Rules, TaxSettings, Vault

from .conftest import stub_auth_header


def _override_chain_deps() -> None:
    app.dependency_overrides[get_chain_client] = lambda: object()
    app.dependency_overrides[get_relayer_signer] = lambda: object()
    app.dependency_overrides[get_vault_factory_address] = lambda: "0xFACTORY"
    app.dependency_overrides[get_yield_pool_address] = lambda: "0xYIELDPOOL"
    app.dependency_overrides[get_default_operator_address] = lambda: "0xOPERATOR"


def _clear_chain_overrides() -> None:
    for dep in (
        get_chain_client,
        get_relayer_signer,
        get_vault_factory_address,
        get_yield_pool_address,
        get_default_operator_address,
    ):
        app.dependency_overrides.pop(dep, None)


def test_create_vault_deploys_and_persists_setup_data(client: TestClient, db_session: Session) -> None:
    _override_chain_deps()
    try:
        fake_deployed = DeployedVault(
            vault_address="0xNEWVAULT",
            income_inbox_address="0xNEWINCOME",
            topup_inbox_address="0xNEWTOPUP",
            tx_hash="0xDEPLOYTXHASH",
        )
        with patch("app.api.routes.vaults.deploy_vault", return_value=fake_deployed) as mock_deploy:
            response = client.post(
                "/v1/vaults",
                json={
                    "country": "US",
                    "income_type": "freelance",
                    "tax_rate_bps": 2000,
                    "tax_delay_hours": 72,
                    "default_kind": "transfer",
                    "known_sources": [{"sender": "0xPAYWALL", "kind": "income", "label": "Paywall"}],
                    "bills": [{"name": "Rent", "amount": 100_000000, "due_date": "2026-11-01T00:00:00Z"}],
                    "goals": [
                        {"name": "Equipment", "target_amount": 5_000_000000, "target_date": "2027-01-01T00:00:00Z"}
                    ],
                    "owner_pay": {"enabled": True, "cap_per_period": 500_000000, "period_days": 7, "buffer_floor": 100_000000},
                },
                headers=stub_auth_header("newuser", "0xNEWUSER"),
            )

        assert response.status_code == 201
        body = response.json()
        assert body["vault_addr"] == "0xNEWVAULT"
        assert mock_deploy.call_count == 1

        _, _, _, deploy_request = mock_deploy.call_args[0]
        assert deploy_request.owner_pay_cap_per_period == 500_000000
        assert deploy_request.min_tax_bps == 2000

        vault = db_session.query(Vault).filter_by(vault_addr="0xNEWVAULT").one()
        assert db_session.query(Rules).filter_by(vault_id=vault.id).one().default_kind == "transfer"
        assert db_session.query(TaxSettings).filter_by(vault_id=vault.id).one().rate_bps == 2000
        assert db_session.query(Bill).filter_by(vault_id=vault.id).count() == 1
        assert db_session.query(Goal).filter_by(vault_id=vault.id).count() == 1
    finally:
        _clear_chain_overrides()


def test_create_vault_rejects_second_vault_for_same_user(client: TestClient, db_session: Session) -> None:
    _override_chain_deps()
    try:
        fake_deployed = DeployedVault(
            vault_address="0xVAULT2",
            income_inbox_address="0xINCOME2",
            topup_inbox_address="0xTOPUP2",
            tx_hash="0xTX2",
        )
        headers = stub_auth_header("dupeuser", "0xDUPEUSER")
        with patch("app.api.routes.vaults.deploy_vault", return_value=fake_deployed):
            first = client.post(
                "/v1/vaults",
                json={"country": "US", "income_type": "freelance", "tax_rate_bps": 2000},
                headers=headers,
            )
            assert first.status_code == 201

            second = client.post(
                "/v1/vaults",
                json={"country": "US", "income_type": "freelance", "tax_rate_bps": 2000},
                headers=headers,
            )
            assert second.status_code == 409
    finally:
        _clear_chain_overrides()


def test_create_vault_requires_auth(client: TestClient) -> None:
    response = client.post("/v1/vaults", json={"country": "US", "income_type": "freelance", "tax_rate_bps": 2000})
    assert response.status_code == 401
