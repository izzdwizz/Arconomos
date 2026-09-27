from app.indexer.classify import DepositKind, KindSource, KnownSourceRule, classify_direct_deposit


def test_direct_deposit_uses_known_source_rule_then_default():
    rules = [KnownSourceRule(sender="0xPAYWALL", kind=DepositKind.INCOME, label="Paywall contract")]

    matched = classify_direct_deposit("0xPAYWALL", rules, default_kind=DepositKind.TRANSFER)
    assert matched.kind == DepositKind.INCOME
    assert matched.kind_source == KindSource.KNOWN_SOURCE
    assert matched.matched_rule.label == "Paywall contract"

    unmatched = classify_direct_deposit("0xSOMEONE_ELSE", rules, default_kind=DepositKind.TRANSFER)
    assert unmatched.kind == DepositKind.TRANSFER
    assert unmatched.kind_source == KindSource.DEFAULT
    assert unmatched.matched_rule is None


def test_known_source_match_is_case_insensitive():
    rules = [KnownSourceRule(sender="0xAbCdEf", kind=DepositKind.INCOME, label="Client")]

    result = classify_direct_deposit("0xabcdef", rules, default_kind=DepositKind.TRANSFER)

    assert result.kind == DepositKind.INCOME
    assert result.kind_source == KindSource.KNOWN_SOURCE
