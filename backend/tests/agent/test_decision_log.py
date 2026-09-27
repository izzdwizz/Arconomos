from app.agent.decision_log import GENESIS_HASH, DecisionLog


def test_logs_decision_before_sending():
    """A decision entry (and its hash) must exist before any transaction is attached to it —
    the log is written first, then updated with tx_hash once the send completes."""
    log = DecisionLog()

    entry = log.append(
        trigger="deposit",
        snapshot={"bucket_balances": {"Tax": 100}},
        proposed=[{"type": "allocate", "params": {}}],
        policy_result={"accepted": True},
        reason="income deposit allocated by current split",
    )

    assert entry.hash is not None
    assert entry.tx_hash is None

    log.attach_tx_hash(entry.id, "0xabc123")
    assert log.entries()[entry.id].tx_hash == "0xabc123"
    # The hash itself never changes once written, even after tx_hash is attached.
    assert log.entries()[entry.id].hash == entry.hash


def test_hash_chain_detects_edit():
    log = DecisionLog()
    log.append("deposit", {}, [], {"accepted": True}, "first")
    log.append("daily", {}, [], {"accepted": True}, "second")

    assert log.verify_chain()

    # Tamper with an already-written entry's reason without recomputing its hash.
    log._entries[0].reason = "tampered"
    assert not log.verify_chain()


def test_first_entry_chains_from_genesis():
    log = DecisionLog()
    entry = log.append("deposit", {}, [], {"accepted": True}, "first")
    assert entry.prev_hash == GENESIS_HASH


def test_entries_are_independent_snapshots():
    """The log must record what the agent saw at decision time; mutating the caller's
    dict afterwards must not retroactively change history."""
    log = DecisionLog()
    snapshot = {"bucket_balances": {"Tax": 100}}
    entry = log.append("deposit", snapshot, [], {"accepted": True}, "first")
    original_hash = entry.hash

    snapshot["bucket_balances"]["Tax"] = 999

    assert entry.snapshot["bucket_balances"]["Tax"] == 100
    assert entry.hash == original_hash
