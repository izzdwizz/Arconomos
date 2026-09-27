"""Executes a policy-approved ProposedAction on-chain: simulate, build, sign, send, wait.

This is the agent's "Act" step. Nothing here decides whether an action is allowed -- that
already happened in app/agent/policy.py; a ProposedAction reaching this module is assumed
accepted. Bucket names/order here must match the Vault contract's `Bucket` enum exactly.
"""

from __future__ import annotations

from web3 import Web3
from web3.contract.contract import ContractFunction

from app.agent.policy import ActionType, ProposedAction
from app.chain.client import ChainClient
from app.chain.signer import OperatorSigner

BUCKET_INDEX = {"Tax": 0, "Bills": 1, "Goals": 2, "OwnerPay": 3, "Buffer": 4, "Savings": 5}
BUCKET_ORDER = ["Tax", "Bills", "Goals", "OwnerPay", "Buffer", "Savings"]


class UnsupportedActionError(Exception):
    pass


def _bps_dict_to_ordered_list(bps_by_name: dict[str, int]) -> list[int]:
    return [bps_by_name[bucket] for bucket in BUCKET_ORDER]


def build_contract_call(
    client: ChainClient,
    vault_address: str,
    action: ProposedAction,
) -> ContractFunction:
    """Turns one approved action into the exact Vault contract call it corresponds to.
    Raises UnsupportedActionError for anything with no on-chain effect (e.g. FLAG)."""
    vault = client.vault(vault_address)

    if action.type == ActionType.ADJUST_SPLIT:
        new_bps = _bps_dict_to_ordered_list(action.params["new_bps"])
        reason_hash = action.params.get("reason_hash", b"\x00" * 32)
        result: ContractFunction = vault.functions.adjustSplit(new_bps, reason_hash)
        return result

    if action.type == ActionType.REBALANCE:
        from_bucket = BUCKET_INDEX[action.params["from_bucket"]]
        to_bucket = BUCKET_INDEX[action.params["to_bucket"]]
        reason_hash = action.params.get("reason_hash", b"\x00" * 32)
        return vault.functions.rebalance(from_bucket, to_bucket, action.params["amount"], reason_hash)

    if action.type == ActionType.SWEEP_TO_YIELD:
        bucket = BUCKET_INDEX[action.params["bucket"]]
        return vault.functions.sweepToYield(bucket, action.params["amount"])

    if action.type == ActionType.REDEEM:
        bucket = BUCKET_INDEX[action.params["bucket"]]
        return vault.functions.redeemFromYield(bucket, action.params["shares"])

    if action.type == ActionType.PAY_OWNER:
        return vault.functions.payOwner(action.params["amount"])

    if action.type == ActionType.ALLOCATE:
        kind = 1 if action.params["kind"] == "income" else 0
        src_tx = action.params.get("src_tx", b"\x00" * 32)
        return vault.functions.allocateDirect(kind, action.params["amount"], src_tx)

    raise UnsupportedActionError(f"{action.type.value} has no on-chain call (FLAG moves no money)")


def execute_action(
    client: ChainClient,
    signer: OperatorSigner,
    vault_address: str,
    action: ProposedAction,
) -> str:
    """Simulates, signs, and sends. Returns the transaction hash (hex string) once it's
    been broadcast -- the caller is responsible for waiting on the receipt and writing it
    into the decision log entry (see app/agent/decision_log.py)."""
    fn = build_contract_call(client, vault_address, action)
    nonce = client.w3.eth.get_transaction_count(Web3.to_checksum_address(signer.address))
    tx = client.build_transaction(fn, from_address=signer.address, nonce=nonce)
    tx_hash = signer.sign_and_send(client.w3, tx)
    return client.w3.to_hex(tx_hash)
