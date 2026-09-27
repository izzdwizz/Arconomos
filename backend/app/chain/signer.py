"""Signs and sends the agent's and relayer's transactions.

Production keys are Circle Wallets (developer-controlled), so they never sit in our env
files. `LocalKeySigner` stands in for that during development and against anvil, the same
way `MockYieldSource` stands in for USYC: same interface, swapped for the real Circle API
client once credentials exist, without touching any call site.
"""

from __future__ import annotations

from typing import Protocol, cast

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_account.types import TransactionDictType
from web3 import Web3
from web3.types import TxParams


class OperatorSigner(Protocol):
    @property
    def address(self) -> str: ...

    def sign_and_send(self, w3: Web3, tx: TxParams) -> bytes: ...


class LocalKeySigner:
    def __init__(self, private_key: str) -> None:
        self._account: LocalAccount = Account.from_key(private_key)

    @property
    def address(self) -> str:
        result: str = self._account.address
        return result

    def sign_and_send(self, w3: Web3, tx: TxParams) -> bytes:
        signed = self._account.sign_transaction(cast(TransactionDictType, dict(tx)))
        tx_hash: bytes = w3.eth.send_raw_transaction(signed.raw_transaction)
        return tx_hash
