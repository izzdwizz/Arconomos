"""App-wide settings, read from the environment (and a local `.env` in dev)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://oikonomos:oikonomos@localhost:5433/oikonomos"
    privy_app_id: str = ""
    privy_app_secret: str = ""
    webhook_signing_secret: str = "dev-only-change-me"
    arc_rpc_url: str = "https://rpc.canteenapp.dev"
    arc_chain_id: int = 5042002
    operator_private_key: str = ""
    openai_api_key: str = ""

    # The relayer deploys vaults on the user's behalf (VaultFactory.deployVault is
    # onlyAdmin), so a brand-new user never needs gas -- see PRD "Setup flow" step 2.
    relayer_private_key: str = ""
    vault_factory_address: str = ""
    yield_pool_address: str = ""
    default_operator_address: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
