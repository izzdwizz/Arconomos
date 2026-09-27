"""Proves app.chain.deploy.deploy_vault (only unit-mocked in tests/api/test_vaults.py)
actually deploys a real vault through the FastAPI endpoint against a live chain.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from web3 import Web3

from app.api.chain_deps import (
    get_chain_client,
    get_default_operator_address,
    get_relayer_signer,
    get_vault_factory_address,
    get_yield_pool_address,
)
from app.api.main import app
from app.chain.client import ChainClient
from app.chain.signer import LocalKeySigner
from app.db.models import Base
from app.db.session import get_db, make_engine

from .anvil_deploy import DEPLOYER_ADDRESS, DEPLOYER_PRIVATE_KEY, OPERATOR_ADDRESS, _deploy

pytestmark = pytest.mark.integration

ANVIL_PORT = 8549
ANVIL_URL = f"http://127.0.0.1:{ANVIL_PORT}"


@pytest.fixture(scope="module")
def anvil_url() -> Generator[str, None, None]:
    proc = subprocess.Popen(
        ["anvil", "--port", str(ANVIL_PORT), "--silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        w3 = Web3(Web3.HTTPProvider(ANVIL_URL))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if w3.is_connected():
                break
            time.sleep(0.2)
        yield ANVIL_URL
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_create_vault_endpoint_deploys_a_real_vault_on_chain(anvil_url: str) -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def _override_get_db() -> Generator[object, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)

    w3 = Web3(Web3.HTTPProvider(anvil_url))
    usdc = _deploy(w3, "MockUSDC.sol/MockUSDC.json")
    factory = _deploy(w3, "VaultFactory.sol/VaultFactory.json", usdc.address, DEPLOYER_ADDRESS)
    yield_pool = _deploy(w3, "YieldPool.sol/YieldPool.json", usdc.address, DEPLOYER_ADDRESS)
    yield_source = _deploy(w3, "MockYieldSource.sol/MockYieldSource.json", usdc.address, yield_pool.address)
    yield_pool.functions.setYieldSource(yield_source.address).transact({"from": DEPLOYER_ADDRESS})

    app.dependency_overrides[get_chain_client] = lambda: ChainClient(w3)
    app.dependency_overrides[get_relayer_signer] = lambda: LocalKeySigner(DEPLOYER_PRIVATE_KEY)
    app.dependency_overrides[get_vault_factory_address] = lambda: factory.address
    app.dependency_overrides[get_yield_pool_address] = lambda: yield_pool.address
    app.dependency_overrides[get_default_operator_address] = lambda: OPERATOR_ADDRESS

    try:
        response = client.post(
            "/v1/vaults",
            json={
                "country": "US",
                "income_type": "freelance",
                "tax_rate_bps": 2000,
                "tax_delay_hours": 72,
                "default_kind": "transfer",
            },
            headers={"Authorization": "Bearer stub:realdeploy:0x1234567890123456789012345678901234567890"},
        )

        assert response.status_code == 201
        body = response.json()

        vault_code = w3.eth.get_code(Web3.to_checksum_address(body["vault_addr"]))
        assert len(vault_code) > 0

        vault_contract = ChainClient(w3).vault(body["vault_addr"])
        assert vault_contract.functions.minTaxBps().call() == 2000
        assert vault_contract.functions.owner().call().lower() == "0x1234567890123456789012345678901234567890"
    finally:
        for dep in (
            get_chain_client,
            get_relayer_signer,
            get_vault_factory_address,
            get_yield_pool_address,
            get_default_operator_address,
            get_db,
        ):
            app.dependency_overrides.pop(dep, None)
