"""Thin wrapper around web3.py: connects to Arc (or a local anvil in tests), builds typed
contract handles from the bundled ABIs, and gives the agent/indexer a place to simulate a
call before it's ever signed and sent.
"""

from __future__ import annotations

from typing import Any, cast

from eth_typing import ABIEvent
from eth_utils.abi import event_abi_to_log_topic
from hexbytes import HexBytes
from web3 import Web3
from web3._utils.events import get_event_data
from web3.contract.contract import Contract, ContractFunction
from web3.types import BlockIdentifier, EventData, Nonce, TxParams

from app.chain.abi import load_abi
from app.core.config import Settings, get_settings


class SimulationRevertedError(Exception):
    """Raised when `eth_call` on a not-yet-sent transaction would revert. The message
    carries the contract's require() string, e.g. 'Vault: operator cannot draw down Tax'."""


class ChainClient:
    def __init__(self, w3: Web3, settings: Settings | None = None) -> None:
        self.w3 = w3
        self.settings = settings or get_settings()

    @classmethod
    def connect(cls, rpc_url: str | None = None) -> ChainClient:
        settings = get_settings()
        url = rpc_url or settings.arc_rpc_url
        return cls(Web3(Web3.HTTPProvider(url)), settings)

    def contract(self, address: str, abi_name: str) -> Contract:
        abi = load_abi(abi_name)
        return self.w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)

    def vault(self, address: str) -> Contract:
        return self.contract(address, "Vault")

    def inbox(self, address: str) -> Contract:
        return self.contract(address, "Inbox")

    def vault_factory(self, address: str) -> Contract:
        return self.contract(address, "VaultFactory")

    def yield_pool(self, address: str) -> Contract:
        return self.contract(address, "YieldPool")

    def erc20(self, address: str) -> Contract:
        return self.contract(address, "MockUSDC")

    # -----------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------

    def get_bucket_balances(self, vault_address: str) -> list[int]:
        return list(self.vault(vault_address).functions.getBucketBalances().call())

    def get_split_bps(self, vault_address: str) -> list[int]:
        return list(self.vault(vault_address).functions.getSplitBps().call())

    def get_total_owned_usdc(self, vault_address: str) -> int:
        result: int = self.vault(vault_address).functions.totalOwnedUsdc().call()
        return result

    def get_guardrails(self, vault_address: str) -> dict[str, int]:
        """Guardrails live on-chain, not cached in Postgres -- the contract is the only
        place that actually enforces them, so the agent reads them fresh each cycle."""
        vault = self.vault(vault_address)
        return {
            "min_tax_bps": vault.functions.minTaxBps().call(),
            "max_split_change_bps_per_week": vault.functions.maxSplitChangeBpsPerWeek().call(),
            "owner_pay_cap_per_period": vault.functions.ownerPayCapPerPeriod().call(),
            "buffer_floor": vault.functions.bufferFloor().call(),
        }

    def get_deposited_events(
        self,
        vault_address: str,
        from_block: BlockIdentifier,
        to_block: BlockIdentifier,
    ) -> list[EventData]:
        vault = self.vault(vault_address)
        return list(vault.events.Deposited().get_logs(from_block=from_block, to_block=to_block))

    def get_all_deposited_events(self, from_block: int, to_block: int) -> list[EventData]:
        """Every vault is a separate contract instance, but they're all clones of the same
        code, so `Deposited`'s event signature (and thus its topic0) is identical across
        all of them. Filtering by topic alone -- no per-vault address -- lets one indexer
        cursor cover every vault in a single call instead of one call per vault per tick.
        """
        deposited_abi_entry = cast(
            ABIEvent,
            next(entry for entry in load_abi("Vault") if entry.get("type") == "event" and entry.get("name") == "Deposited"),
        )
        topic0 = Web3.to_hex(event_abi_to_log_topic(deposited_abi_entry))
        raw_logs = self.w3.eth.get_logs({"fromBlock": from_block, "toBlock": to_block, "topics": [topic0]})
        return [get_event_data(self.w3.codec, deposited_abi_entry, log) for log in raw_logs]

    def get_allocated_events(
        self,
        vault_address: str,
        from_block: BlockIdentifier,
        to_block: BlockIdentifier,
    ) -> list[EventData]:
        vault = self.vault(vault_address)
        return list(vault.events.Allocated().get_logs(from_block=from_block, to_block=to_block))

    # -----------------------------------------------------------------
    # Writes: simulate first, build the transaction, sign+send is the caller's job
    # -----------------------------------------------------------------

    def simulate(self, fn: ContractFunction, tx: TxParams) -> Any:
        """Dry-runs `fn` via eth_call with the same params the real send would use. A
        revert here means the guardrail or another require() would have rejected it
        on-chain -- caught before spending real gas, per the agent's "Check" step."""
        try:
            return fn.call(tx)
        except Exception as exc:  # web3 raises ContractLogicError / Web3RPCError variants
            raise SimulationRevertedError(str(exc)) from exc

    def build_transaction(self, fn: ContractFunction, from_address: str, nonce: int, chain_id: int | None = None) -> TxParams:
        # The connected node's own chain ID is authoritative -- app settings default to Arc's,
        # but the same code also runs against a local anvil (chain 31337) in tests, and a
        # mismatch here is rejected by web3's own signing validation before it ever reaches
        # the network.
        tx: TxParams = {
            "from": Web3.to_checksum_address(from_address),
            "nonce": Nonce(nonce),
            "chainId": chain_id or self.w3.eth.chain_id,
        }
        self.simulate(fn, tx)
        built: TxParams = fn.build_transaction(tx)
        return built

    def wait_for_receipt(self, tx_hash: bytes, timeout: int = 120) -> dict[str, Any]:
        receipt = self.w3.eth.wait_for_transaction_receipt(HexBytes(tx_hash), timeout=timeout)
        return dict(receipt)
