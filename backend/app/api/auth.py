"""Privy token verification. Every user-facing request authenticates with a Privy access
token, which we verify server-side; every integrator request instead carries an API key
scoped to one vault (see integrations router).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db


@dataclass(frozen=True)
class VerifiedIdentity:
    privy_id: str
    wallet: str


class PrivyClient(Protocol):
    def verify_access_token(self, token: str) -> VerifiedIdentity: ...


class InvalidPrivyTokenError(Exception):
    pass


class StubPrivyClient:
    """Verifies tokens issued by tests/dev tooling: `f"stub:{privy_id}:{wallet}"`.

    Swapped for the real `privy_client.PrivyAPI(...).verify_auth_token()` call once the
    Privy app credentials are configured; kept behind the same `PrivyClient` protocol so
    the swap touches only app/core/config.py and this module's dependency wiring.
    """

    def verify_access_token(self, token: str) -> VerifiedIdentity:
        if not token.startswith("stub:"):
            raise InvalidPrivyTokenError("not a recognized token")
        parts = token.split(":", 2)
        if len(parts) != 3:
            raise InvalidPrivyTokenError("malformed stub token")
        _, privy_id, wallet = parts
        return VerifiedIdentity(privy_id=privy_id, wallet=wallet)


def get_privy_client() -> PrivyClient:
    return StubPrivyClient()


def get_bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return header[len("bearer ") :].strip()


def get_current_user(
    token: str = Depends(get_bearer_token),
    privy: PrivyClient = Depends(get_privy_client),
    db: Session = Depends(get_db),
) -> User:
    try:
        identity = privy.verify_access_token(token)
    except InvalidPrivyTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc

    user = db.execute(select(User).where(User.privy_id == identity.privy_id)).scalar_one_or_none()
    if user is None:
        user = User(privy_id=identity.privy_id, wallet=identity.wallet)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
