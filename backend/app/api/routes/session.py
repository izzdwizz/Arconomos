from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.models import User

from ..auth import get_current_user

router = APIRouter(tags=["session"])


@router.post("/v1/session")
def create_session(user: User = Depends(get_current_user)) -> dict[str, str]:
    """Verifies the Privy token and creates the user on first sign-in (both handled by the
    get_current_user dependency itself)."""
    return {"id": user.id, "wallet": user.wallet}
