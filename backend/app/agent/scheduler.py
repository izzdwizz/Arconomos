"""When the agent runs (PRD "Agent design > When it runs"): on every deposit, daily,
weekly, and on an owner action. This module owns the daily/weekly recurring jobs; the
per-deposit and on-owner-action triggers are called directly by the indexer and the API's
owner-intent endpoint respectively, not scheduled here.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.cycle import run_cycle
from app.agent.locking import vault_lock
from app.agent.model_client import ModelClient
from app.chain.actions import execute_action
from app.chain.client import ChainClient
from app.chain.signer import OperatorSigner
from app.db.models import Vault
from app.indexer.poller import run_indexer_tick

logger = logging.getLogger(__name__)

INDEXER_POLL_INTERVAL_SECONDS = 15


def run_cycle_for_all_vaults(
    session_factory: sessionmaker[Session],
    chain_client: ChainClient,
    signer: OperatorSigner,
    model_client: ModelClient,
    trigger: str,
) -> None:
    """One tick of a scheduled job: iterate every vault, skipping any another worker
    already holds the lock for (see app/agent/locking.py) rather than blocking on it."""
    db = session_factory()
    try:
        vault_ids = db.execute(select(Vault.id)).scalars().all()
    finally:
        db.close()

    for vault_id in vault_ids:
        db = session_factory()
        try:
            with vault_lock(db, vault_id) as acquired:
                if not acquired:
                    logger.info("skipping vault %s this tick: another worker holds its lock", vault_id)
                    continue
                vault = db.get(Vault, vault_id)
                if vault is None:
                    continue
                try:
                    run_cycle(
                        db,
                        chain_client,
                        signer,
                        vault,
                        trigger=trigger,
                        model_client=model_client,
                        execute_action_fn=execute_action,
                    )
                except Exception:
                    # One vault's cycle failing must never take down the scheduler or
                    # block every other vault's cycle this tick.
                    logger.exception("agent cycle failed for vault %s (trigger=%s)", vault_id, trigger)
        finally:
            db.close()


def poll_indexer(
    session_factory: sessionmaker[Session],
    chain_client: ChainClient,
    signer: OperatorSigner,
    model_client: ModelClient,
) -> None:
    """One indexer tick: scan for new deposits chain-wide and trigger a deposit-driven
    cycle for any vault that got one. See app/indexer/poller.py."""
    db = session_factory()
    try:
        run_indexer_tick(
            db,
            chain_client,
            signer,
            model_client,
            chain_id=chain_client.w3.eth.chain_id,
            execute_action_fn=execute_action,
        )
    except Exception:
        # A bad tick (RPC hiccup, etc.) must not kill the recurring job -- the next tick
        # just tries again from wherever the cursor last landed.
        logger.exception("indexer poll tick failed")
    finally:
        db.close()


def build_scheduler(
    session_factory: sessionmaker[Session],
    chain_client: ChainClient,
    signer: OperatorSigner,
    model_client: ModelClient,
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        run_cycle_for_all_vaults,
        trigger=CronTrigger(hour=6, minute=0),
        args=[session_factory, chain_client, signer, model_client, "daily"],
        id="daily-cycle",
        replace_existing=True,
    )
    scheduler.add_job(
        run_cycle_for_all_vaults,
        trigger=CronTrigger(day_of_week="mon", hour=7, minute=0),
        args=[session_factory, chain_client, signer, model_client, "weekly"],
        id="weekly-cycle",
        replace_existing=True,
    )
    scheduler.add_job(
        poll_indexer,
        trigger=IntervalTrigger(seconds=INDEXER_POLL_INTERVAL_SECONDS),
        args=[session_factory, chain_client, signer, model_client],
        id="indexer-poll",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler
