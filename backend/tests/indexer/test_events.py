from app.indexer.classify import DepositKind
from app.indexer.events import DepositedEvent, record_inbox_deposit


def test_transfer_to_income_inbox_recorded_as_income():
    event = DepositedEvent(
        tx_hash="0xdeadbeef",
        log_index=3,
        block_number=1000,
        vault_address="0xVAULT",
        inbox="0xINCOME_INBOX",
        kind=DepositKind.INCOME,
        amount=100_000000,
        src_tx="0xdeadbeef",
    )

    row = record_inbox_deposit(event)

    assert row["kind"] == DepositKind.INCOME
    assert row["kind_source"] == "inbox"
    assert row["sender"] == "0xINCOME_INBOX"
    assert row["amount"] == 100_000000
