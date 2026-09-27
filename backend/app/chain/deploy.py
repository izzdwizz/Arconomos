"""Deploys a user's Vault + Inbox pair via the relayer (VaultFactory.deployVault is
onlyAdmin, our relayer is admin), so a brand-new user needs no gas -- PRD "Setup flow"
step 2.
"""

from __future__ import annotations

from dataclasses import dataclass

from hexbytes import HexBytes
from web3 import Web3

from app.chain.client import ChainClient
from app.chain.signer import OperatorSigner


@dataclass(frozen=True)
class DeployedVault:
    vault_address: str
    income_inbox_address: str
    topup_inbox_address: str
    tx_hash: str


@dataclass(frozen=True)
class VaultDeployRequest:
    user_address: str
    operator_address: str
    payout_address: str
    yield_pool_address: str
    min_tax_bps: int
    max_split_change_bps_per_week: int
    tax_withdraw_delay_seconds: int
    owner_pay_cap_per_period: int
    owner_pay_period_seconds: int
    buffer_floor: int


def deploy_vault(
    client: ChainClient,
    relayer_signer: OperatorSigner,
    factory_address: str,
    request: VaultDeployRequest,
) -> DeployedVault:
    factory = client.vault_factory(factory_address)
    deploy_request = (
        Web3.to_checksum_address(request.user_address),
        Web3.to_checksum_address(request.operator_address),
        Web3.to_checksum_address(request.payout_address),
        Web3.to_checksum_address(request.yield_pool_address),
        request.min_tax_bps,
        request.max_split_change_bps_per_week,
        request.tax_withdraw_delay_seconds,
        request.owner_pay_cap_per_period,
        request.owner_pay_period_seconds,
        request.buffer_floor,
    )
    fn = factory.functions.deployVault(deploy_request)
    relayer_address = Web3.to_checksum_address(relayer_signer.address)
    nonce = client.w3.eth.get_transaction_count(relayer_address)
    tx = client.build_transaction(fn, from_address=relayer_address, nonce=nonce)
    tx_hash = relayer_signer.sign_and_send(client.w3, tx)
    receipt = client.w3.eth.wait_for_transaction_receipt(HexBytes(tx_hash))

    deployed_events = factory.events.VaultDeployed().process_receipt(receipt)
    args = deployed_events[0]["args"]
    return DeployedVault(
        vault_address=args["vault"],
        income_inbox_address=args["incomeInbox"],
        topup_inbox_address=args["topupInbox"],
        tx_hash=client.w3.to_hex(tx_hash),
    )
