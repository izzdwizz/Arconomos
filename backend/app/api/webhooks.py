"""HMAC-SHA256 signing for outgoing webhooks (`deposit.received`, `deposit.allocated`,
`decision.made`, `flag.raised`, `owner.paid`), so a receiver can verify the payload came
from us and wasn't altered in transit.
"""

from __future__ import annotations

import hashlib
import hmac


def sign_payload(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, raw_body: bytes, signature: str) -> bool:
    expected = sign_payload(secret, raw_body)
    return hmac.compare_digest(expected, signature)
