from app.indexer.ledger import Ledger, RawDepositLog


def _log(tx_hash: str, log_index: int, block_number: int, amount: int = 100) -> RawDepositLog:
    return RawDepositLog(
        tx_hash=tx_hash,
        log_index=log_index,
        inbox_or_vault="0xVAULT",
        sender="0xSENDER",
        amount=amount,
        block_number=block_number,
    )


def test_reorg_safe_cursor():
    """Reprocessing a block range (as happens after a reorg rewinds the cursor) must create
    no duplicate ledger rows — rows are keyed on (tx_hash, log_index), which is stable even
    if the block that tx ends up in changes across a reorg."""
    ledger = Ledger()

    first_pass = [_log("0xaaa", 0, block_number=100), _log("0xbbb", 0, block_number=101)]
    inserted_first = ledger.record_deposits(first_pass)
    assert len(inserted_first) == 2
    assert len(ledger.all_rows()) == 2

    # Reorg: cursor rewinds, the same range (plus a genuinely new log) is processed again.
    replay_with_new_log = [
        _log("0xaaa", 0, block_number=100),
        _log("0xbbb", 0, block_number=101),
        _log("0xccc", 0, block_number=102),
    ]
    inserted_second = ledger.record_deposits(replay_with_new_log)

    assert len(inserted_second) == 1
    assert inserted_second[0].tx_hash == "0xccc"
    assert len(ledger.all_rows()) == 3


def test_same_tx_different_log_index_are_distinct_rows():
    ledger = Ledger()
    logs = [_log("0xaaa", 0, block_number=100), _log("0xaaa", 1, block_number=100)]

    inserted = ledger.record_deposits(logs)

    assert len(inserted) == 2
