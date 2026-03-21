"""Liquidity and tradability filters for white-box risk."""

from __future__ import annotations

import pandas as pd


def apply_liquidity_filters(
    df: pd.DataFrame,
    *,
    min_close: float = 0.0,
    max_close: float = 0.0,
    min_amount: float = 0.0,
    min_turnover: float = 0.0,
    min_volume: float = 0.0,
) -> pd.DataFrame:
    working = df.copy()

    if "close" in working.columns and min_close > 0:
        working = working[working["close"] >= min_close]
    if "close" in working.columns and max_close > 0:
        working = working[working["close"] <= max_close]
    if "amount" in working.columns and min_amount > 0:
        working = working[working["amount"] >= min_amount]
    if "turnover" in working.columns and min_turnover > 0:
        working = working[working["turnover"] >= min_turnover]
    if "volume" in working.columns and min_volume > 0:
        working = working[working["volume"] >= min_volume]

    return working.copy()
