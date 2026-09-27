"""API-side chain wiring: a ChainClient for reads, and the relayer's signer for the one
write the API itself makes -- deploying a new vault. Everything else the operator does
(splits, sweeps, pay) runs from the agent worker, not from an API request handler.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException, status
from web3 import Web3

from app.chain.client import ChainClient
from app.chain.signer import LocalKeySigner, OperatorSigner
from app.core.config import get_settings


@lru_cache
def get_chain_client() -> ChainClient:
    return ChainClient.connect()


def get_relayer_signer() -> OperatorSigner:
    key = get_settings().relayer_private_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RELAYER_PRIVATE_KEY is not configured; vault deployment is unavailable",
        )
    return LocalKeySigner(key)


def get_vault_factory_address() -> str:
    address = get_settings().vault_factory_address
    if not address:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAULT_FACTORY_ADDRESS is not configured; vault deployment is unavailable",
        )
    return Web3.to_checksum_address(address)


def get_yield_pool_address() -> str:
    address = get_settings().yield_pool_address
    if not address:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YIELD_POOL_ADDRESS is not configured; vault deployment is unavailable",
        )
    return Web3.to_checksum_address(address)


def get_default_operator_address() -> str:
    address = get_settings().default_operator_address
    if not address:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEFAULT_OPERATOR_ADDRESS is not configured; vault deployment is unavailable",
        )
    return Web3.to_checksum_address(address)
