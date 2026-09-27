"""Weekly income/spend forecasting. Pure arithmetic — no model calls here.

Deterministic code produces the numbers; the model only chooses and explains actions
from what this module hands it (see app/agent/planner.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class WeekBand:
    week: int
    income_low: float
    income_mid: float
    income_high: float
    needed: float


@dataclass(frozen=True)
class Forecast:
    weeks: list[WeekBand]

    def week(self, n: int) -> WeekBand:
        return self.weeks[n]


def forecast_income(
    weekly_income_history: list[float],
    setup_monthly_income: float,
    horizon_weeks: int = 12,
    needed_per_week: float | None = None,
) -> Forecast:
    """Median income per week with low/high bands, resampled from recent history.

    Cold start (fewer than 4 weeks of history): the setup-time monthly income estimate
    stands in for the median, with wide bands reflecting the lack of real data yet.
    """
    needed = needed_per_week if needed_per_week is not None else 0.0

    if len(weekly_income_history) < 4:
        setup_weekly = setup_monthly_income / 4.0
        weeks = [
            WeekBand(
                week=i,
                income_low=setup_weekly * 0.5,
                income_mid=setup_weekly,
                income_high=setup_weekly * 1.5,
                needed=needed,
            )
            for i in range(horizon_weeks)
        ]
        return Forecast(weeks=weeks)

    history = np.array(weekly_income_history, dtype=float)
    rng = np.random.default_rng(seed=42)
    resampled_medians = np.array(
        [np.median(rng.choice(history, size=len(history), replace=True)) for _ in range(1000)]
    )
    low, mid, high = np.percentile(resampled_medians, [10, 50, 90])

    weeks = [
        WeekBand(week=i, income_low=float(low), income_mid=float(mid), income_high=float(high), needed=needed)
        for i in range(horizon_weeks)
    ]
    return Forecast(weeks=weeks)


def bill_needs_over_horizon(
    bills: list[dict[str, Any]],
    horizon_days: int = 20,
    as_of: pd.Timestamp | None = None,
) -> float:
    """Sum of bill amounts due within the horizon."""
    as_of = as_of or pd.Timestamp.now(tz="UTC")
    cutoff = as_of + pd.Timedelta(days=horizon_days)
    total = 0.0
    for bill in bills:
        due = pd.Timestamp(bill["due_date"])
        if due.tzinfo is None:
            due = due.tz_localize("UTC")
        if as_of <= due <= cutoff:
            total += bill["amount"]
    return total
