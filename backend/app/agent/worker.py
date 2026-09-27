"""Entry point for the agent process (one of the three: api, indexer, agent -- see PRD
repo layout). Starts the daily/weekly scheduler and blocks. Deposit-triggered and
owner-action-triggered cycles are invoked directly by the indexer and API processes, not
from here.
"""

from __future__ import annotations

import logging
import signal
import time
from types import FrameType

from sqlalchemy.orm import sessionmaker

from app.agent.model_client import OpenAIModelClient, ScriptedModelClient
from app.agent.scheduler import build_scheduler
from app.chain.client import ChainClient
from app.chain.signer import LocalKeySigner
from app.core.config import get_settings
from app.db.session import make_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    engine = make_engine()
    session_factory = sessionmaker(bind=engine)

    chain_client = ChainClient.connect(settings.arc_rpc_url)

    operator_key = settings.operator_private_key
    if not operator_key:
        raise RuntimeError("OPERATOR_PRIVATE_KEY is not set; the agent has no key to sign with")
    signer = LocalKeySigner(operator_key)

    model_client = (
        OpenAIModelClient(api_key=settings.openai_api_key) if settings.openai_api_key else ScriptedModelClient()
    )
    if isinstance(model_client, ScriptedModelClient):
        logger.warning("OPENAI_API_KEY not set -- running with ScriptedModelClient, not the real model")

    scheduler = build_scheduler(session_factory, chain_client, signer, model_client)
    scheduler.start()
    logger.info("agent scheduler started (daily 06:00, weekly Mon 07:00)")

    running = True

    def _handle_shutdown(signum: int, frame: FrameType | None) -> None:
        nonlocal running
        logger.info("received signal %s, shutting down", signum)
        running = False

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    try:
        while running:
            time.sleep(1)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    main()
