import json

from app.api.webhooks import sign_payload, verify_signature


def test_webhook_signature() -> None:
    secret = "whsec_test"
    body = json.dumps({"event": "deposit.allocated", "amount": 5000}).encode()

    signature = sign_payload(secret, body)

    assert verify_signature(secret, body, signature)


def test_webhook_signature_rejects_tampered_body() -> None:
    secret = "whsec_test"
    body = json.dumps({"event": "deposit.allocated", "amount": 5000}).encode()
    signature = sign_payload(secret, body)

    tampered_body = json.dumps({"event": "deposit.allocated", "amount": 999999}).encode()

    assert not verify_signature(secret, tampered_body, signature)


def test_webhook_signature_rejects_wrong_secret() -> None:
    body = json.dumps({"event": "owner.paid", "amount": 100}).encode()
    signature = sign_payload("correct-secret", body)

    assert not verify_signature("wrong-secret", body, signature)
