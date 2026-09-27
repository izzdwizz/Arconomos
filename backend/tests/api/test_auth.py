from fastapi.testclient import TestClient

from .conftest import stub_auth_header


def test_privy_token_required(client: TestClient) -> None:
    response = client.get("/v1/vaults/me")
    assert response.status_code == 401


def test_malformed_bearer_token_rejected(client: TestClient) -> None:
    response = client.get("/v1/vaults/me", headers={"Authorization": "Bearer not-a-stub-token"})
    assert response.status_code == 401


def test_valid_token_but_no_vault_yet_returns_404(client: TestClient) -> None:
    response = client.get("/v1/vaults/me", headers=stub_auth_header("privy-1", "0xWALLET1"))
    assert response.status_code == 404


def test_session_creates_user_on_first_sign_in(client: TestClient) -> None:
    response = client.post("/v1/session", headers=stub_auth_header("privy-1", "0xWALLET1"))
    assert response.status_code == 200
    assert response.json()["wallet"] == "0xWALLET1"

    # Second call with the same identity reuses the same user, doesn't create a duplicate.
    second = client.post("/v1/session", headers=stub_auth_header("privy-1", "0xWALLET1"))
    assert second.json()["id"] == response.json()["id"]
