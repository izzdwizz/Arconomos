"""Runs one indexer tick: scan new `Deposited` events chain-wide, record them, refresh the
bucket-balance cache for any vault that got a new deposit, and trigger that vault's agent
cycle -- PRD "When it runs": "on every deposit: allocate by the current split (mechanical,
no model call), then check whether anything should change."

A single global cursor (see app/db/models.py IndexerCursor) covers every vault at once,
since all vaults share the same Deposited event signature -- see
ChainClient.get_all_deposited_events for why that lets one topic-only filter do the work
of scanning every vault individually.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.cycle import ActionExecutor, run_cycle
from app.agent.locking import vault_lock
from app.agent.model_client import ModelClient
from app.chain.client import ChainClient
from app.chain.signer import OperatorSigner
from app.db.models import BucketBalance, Deposit, IndexerCursor, Vault
from app.indexer.events import record_inbox_deposit
from app.indexer.scanner import scan_all_deposited_events

logger = logging.getLogger(__name__)

BUCKETS = ["Tax", "Bills", "Goals", "OwnerPay", "Buffer", "Savings"]


class DepositTrigger(Protocol):
    def __call__(
        self,
        db: Session,
        chain_client: ChainClient,
        signer: OperatorSigner,
        vault: Vault,
        trigger: str,
        model_client: ModelClient,
        execute_action_fn: ActionExecutor,
    ) -> object: ...


def _get_or_create_cursor(db: Session, chain_id: int) -> IndexerCursor:
    cursor = db.get(IndexerCursor, chain_id)
    if cursor is None:
        cursor = IndexerCursor(chain_id=chain_id, last_block=0)
        db.add(cursor)
        db.flush()
    return cursor


def _refresh_bucket_balances(db: Session, chain_client: ChainClient, vault: Vault, as_of_block: int) -> None:
    balances = chain_client.get_bucket_balances(vault.vault_addr)
    for bucket_name, amount in zip(BUCKETS, balances, strict=True):
        row = db.execute(
            select(BucketBalance).where(BucketBalance.vault_id == vault.id, BucketBalance.bucket == bucket_name)
        ).scalar_one_or_none()
        if row is None:
            db.add(BucketBalance(vault_id=vault.id, bucket=bucket_name, amount=amount, as_of_block=as_of_block))
        else:
            row.amount = amount
            row.as_of_block = as_of_block


def run_indexer_tick(
    db: Session,
    chain_client: ChainClient,
    signer: OperatorSigner,
    model_client: ModelClient,
    chain_id: int,
    execute_action_fn: ActionExecutor,
    trigger_deposit_cycle: DepositTrigger = run_cycle,
) -> dict[str, int]:
    """Returns {vault_id: new_deposit_count} for vaults that got at least one new deposit
    this tick (and therefore had a deposit-triggered cycle run)."""
    cursor = _get_or_create_cursor(db, chain_id)
    latest_block = chain_client.w3.eth.block_number
    if latest_block < cursor.last_block:
        return {}

    events = scan_all_deposited_events(chain_client, cursor.last_block, latest_block)

    vaults_by_address = {
        v.vault_addr.lower(): v for v in db.execute(select(Vault)).scalars().all()
    }

    new_deposit_counts: dict[str, int] = defaultdict(int)
    for event in events:
        vault = vaults_by_address.get(event.vault_address.lower())
        if vault is None:
            # A Deposited log from a contract we don't recognize as one of our vaults --
            # shouldn't happen since the topic is specific to our Vault bytecode, but a
            # stray match is data, not a reason to crash the whole tick.
            logger.warning("Deposited event from unrecognized vault address %s", event.vault_address)
            continue

        row = record_inbox_deposit(event)
        deposit = Deposit(
            vault_id=vault.id,
            tx_hash=row["tx_hash"],
            log_index=row["log_index"],
            sender=row["sender"],
            amount=row["amount"],
            kind=row["kind"].value,
            kind_source=row["kind_source"],
            block_number=event.block_number,
        )
        db.add(deposit)
        try:
            db.flush()
        except IntegrityError:
            # Already recorded (e.g. cursor re-processing a range after a reorg) --
            # see tests/indexer/test_ledger.py for the same idempotency guarantee.
            db.rollback()
            continue
        new_deposit_counts[vault.id] += 1

    cursor.last_block = latest_block
    db.commit()

    for vault_id in new_deposit_counts:
        vault = db.get(Vault, vault_id)
        if vault is None:
            continue
        _refresh_bucket_balances(db, chain_client, vault, latest_block)
        db.commit()

        # Same advisory lock the daily/weekly scheduler uses (app/agent/locking.py): a
        # deposit can land in the same tick a cron cycle is already running for this
        # vault, and only one of them may act on it at a time.
        with vault_lock(db, vault_id) as acquired:
            if not acquired:
                logger.info("skipping deposit-triggered cycle for vault %s: locked by another worker", vault_id)
                continue
            try:
                trigger_deposit_cycle(
                    db,
                    chain_client,
                    signer,
                    vault,
                    trigger="deposit",
                    model_client=model_client,
                    execute_action_fn=execute_action_fn,
                )
            except Exception:
                logger.exception("deposit-triggered agent cycle failed for vault %s", vault_id)

    return dict(new_deposit_counts)
