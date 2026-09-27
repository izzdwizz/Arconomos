from hypothesis import given
from hypothesis import strategies as st

from app.agent.forecast import bill_needs_over_horizon, forecast_income


def test_cold_start_uses_setup_income():
    forecast = forecast_income(weekly_income_history=[], setup_monthly_income=4000.0, horizon_weeks=12)

    assert len(forecast.weeks) == 12
    for week in forecast.weeks:
        assert week.income_mid == 1000.0
        assert week.income_low < week.income_mid < week.income_high


def test_cold_start_with_a_couple_weeks_still_uses_setup_income():
    forecast = forecast_income(
        weekly_income_history=[900.0, 1100.0], setup_monthly_income=4000.0, horizon_weeks=4
    )
    assert forecast.week(0).income_mid == 1000.0


@given(st.floats(min_value=0.05, max_value=2.0))
def test_bands_widen_with_volatile_income(volatility_multiplier: float):
    stable_history = [1000.0] * 12
    volatile_history = [1000.0 + (i % 2 * 2 - 1) * 1000.0 * volatility_multiplier for i in range(12)]

    stable_forecast = forecast_income(stable_history, setup_monthly_income=4000.0)
    volatile_forecast = forecast_income(volatile_history, setup_monthly_income=4000.0)

    stable_width = stable_forecast.week(0).income_high - stable_forecast.week(0).income_low
    volatile_width = volatile_forecast.week(0).income_high - volatile_forecast.week(0).income_low

    assert volatile_width >= stable_width


def test_bill_needs_over_horizon_sums_only_bills_due_within_window():
    import pandas as pd

    as_of = pd.Timestamp("2026-10-01", tz="UTC")
    bills = [
        {"amount": 100.0, "due_date": "2026-10-05"},  # within 20 days
        {"amount": 200.0, "due_date": "2026-11-15"},  # outside
    ]
    assert bill_needs_over_horizon(bills, horizon_days=20, as_of=as_of) == 100.0
