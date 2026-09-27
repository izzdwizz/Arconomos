"""Shared FastAPI dependencies beyond user auth: vault scoping and integration API keys."""

from __future__ import annotations

import hashlib
import secrets

from fastapi import Depends, Header, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Integration, User, Vault
from app.db.session import get_db

from .auth import get_current_user


def get_current_vault(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Vault:
    vault = db.execute(select(Vault).where(Vault.user_id == user.id)).scalar_one_or_none()
    if vault is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no vault for this user yet")
    return vault


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key_shown_once, key_hash_to_store)."""
    raw_key = f"oik_{secrets.token_urlsafe(32)}"
    return raw_key, hash_api_key(raw_key)


def get_integration_for_request(
    integration_id: str = Path(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Integration:
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing API key")

    integration = db.execute(select(Integration).where(Integration.id == integration_id)).scalar_one_or_none()
    if integration is None or integration.key_hash != hash_api_key(x_api_key):
        # Same response for "no such integration" and "wrong key": don't confirm existence.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    return integration
