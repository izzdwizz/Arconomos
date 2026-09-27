"""Test-only helper: deploys the full contract stack to a local anvil node.

Reads full artifacts (ABI + bytecode) straight from contracts/out -- unlike app/chain/abi.py,
which only ever needs the bundled ABI to call already-deployed contracts, this needs the
bytecode too, so it stays out of the shipped backend package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eth_account import Account
from web3 import Web3
from web3.contract.contract import Contract

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_OUT = REPO_ROOT / "contracts" / "out"

# anvil's well-known deterministic dev accounts (mnemonic "test test test ... junk").
# Never used with real funds; safe to hardcode for local-only test deployment. Addresses
# are derived from the keys rather than hardcoded separately, so the two can't drift apart.
DEPLOYER_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
OPERATOR_PRIVATE_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
DEPLOYER_ADDRESS = Account.from_key(DEPLOYER_PRIVATE_KEY).address
OPERATOR_ADDRESS = Account.from_key(OPERATOR_PRIVATE_KEY).address


def _load_artifact(relpath: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_OUT / relpath).read_text())  # type: ignore[no-any-return]


def _deploy(w3: Web3, relpath: str, *args: Any) -> Contract:
    artifact = _load_artifact(relpath)
    factory = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"]["object"])
    tx_hash = factory.constructor(*args).transact({"from": DEPLOYER_ADDRESS})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return w3.eth.contract(address=receipt["contractAddress"], abi=artifact["abi"])


@dataclass(frozen=True)
class DeployedStack:
    usdc: Contract
    factory: Contract
    yield_pool: Contract
    yield_source: Contract
    vault_address: str
    income_inbox_address: str
    topup_inbox_address: str


def deploy_stack(
    w3: Web3,
    min_tax_bps: int = 2000,
    max_split_change_bps: int = 1000,
    tax_delay_seconds: int = 72 * 3600,
    owner_pay_cap: int = 500 * 10**6,
    owner_pay_period: int = 7 * 24 * 3600,
    buffer_floor: int = 0,
) -> DeployedStack:
    usdc = _deploy(w3, "MockUSDC.sol/MockUSDC.json")
    factory = _deploy(w3, "VaultFactory.sol/VaultFactory.json", usdc.address, DEPLOYER_ADDRESS)

    yield_pool = _deploy(w3, "YieldPool.sol/YieldPool.json", usdc.address, DEPLOYER_ADDRESS)
    yield_source = _deploy(w3, "MockYieldSource.sol/MockYieldSource.json", usdc.address, yield_pool.address)
    yield_pool.functions.setYieldSource(yield_source.address).transact({"from": DEPLOYER_ADDRESS})

    deploy_request = (
        DEPLOYER_ADDRESS,
        OPERATOR_ADDRESS,
        DEPLOYER_ADDRESS,
        yield_pool.address,
        min_tax_bps,
        max_split_change_bps,
        tax_delay_seconds,
        owner_pay_cap,
        owner_pay_period,
        buffer_floor,
    )
    deploy_tx = factory.functions.deployVault(deploy_request).transact({"from": DEPLOYER_ADDRESS})
    receipt = w3.eth.wait_for_transaction_receipt(deploy_tx)

    deployed_events = factory.events.VaultDeployed().process_receipt(receipt)
    args = deployed_events[0]["args"]
    vault_address, income_inbox, topup_inbox = args["vault"], args["incomeInbox"], args["topupInbox"]

    yield_pool.functions.registerVault(vault_address).transact({"from": DEPLOYER_ADDRESS})

    return DeployedStack(
        usdc=usdc,
        factory=factory,
        yield_pool=yield_pool,
        yield_source=yield_source,
        vault_address=vault_address,
        income_inbox_address=income_inbox,
        topup_inbox_address=topup_inbox,
    )
