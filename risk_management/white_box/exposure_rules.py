"""Group exposure controls for white-box risk."""

from __future__ import annotations

import numpy as np
import pandas as pd


def assign_quantile_bucket(series: pd.Series, labels: list[str]) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    result = pd.Series(["unknown"] * len(values), index=values.index, dtype="object")
    valid = values.dropna()
    if valid.empty:
        return result
    rank_pct = valid.rank(method="average", pct=True)
    bucket_codes = np.minimum((rank_pct * len(labels)).astype(int), len(labels) - 1)
    result.loc[valid.index] = [labels[int(code)] for code in bucket_codes]
    return result


def ensure_group_columns(df: pd.DataFrame, requested_columns: list[str]) -> pd.DataFrame:
    working = df.copy()
    for column in requested_columns:
        if not column or column in working.columns:
            continue
        if column == "amount_bucket" and "amount" in working.columns:
            working[column] = working.groupby("date")["amount"].transform(
                lambda series: assign_quantile_bucket(
                    series, ["liq_low", "liq_mid_low", "liq_mid", "liq_mid_high", "liq_high"]
                )
            )
        elif column == "turnover_bucket" and "turnover" in working.columns:
            working[column] = working.groupby("date")["turnover"].transform(
                lambda series: assign_quantile_bucket(
                    series, ["turn_low", "turn_mid_low", "turn_mid", "turn_mid_high", "turn_high"]
                )
            )
        elif column == "price_bucket_dynamic" and "close" in working.columns:
            working[column] = working.groupby("date")["close"].transform(
                lambda series: assign_quantile_bucket(
                    series, ["price_low", "price_mid_low", "price_mid", "price_mid_high", "price_high"]
                )
            )
    return working


def capped_selection(
    eligible: pd.DataFrame,
    *,
    score_column: str,
    top_k: int,
    group_column: str = "",
    max_per_group: int = 0,
    secondary_group_column: str = "",
    secondary_max_per_group: int = 0,
) -> pd.DataFrame:
    if not group_column and not secondary_group_column:
        return eligible.sort_values(score_column, ascending=False, kind="stable").head(top_k)

    selected_rows: list[int] = []
    primary_counts: dict[object, int] = {}
    secondary_counts: dict[object, int] = {}

    ordered = eligible.sort_values(score_column, ascending=False, kind="stable")
    for idx, row in ordered.iterrows():
        if len(selected_rows) >= top_k:
            break

        primary_ok = True
        if group_column and max_per_group > 0:
            primary_value = row.get(group_column, "unknown")
            primary_ok = primary_counts.get(primary_value, 0) < max_per_group
        else:
            primary_value = None

        secondary_ok = True
        if secondary_group_column and secondary_max_per_group > 0:
            secondary_value = row.get(secondary_group_column, "unknown")
            secondary_ok = secondary_counts.get(secondary_value, 0) < secondary_max_per_group
        else:
            secondary_value = None

        if not (primary_ok and secondary_ok):
            continue

        selected_rows.append(idx)
        if primary_value is not None:
            primary_counts[primary_value] = primary_counts.get(primary_value, 0) + 1
        if secondary_value is not None:
            secondary_counts[secondary_value] = secondary_counts.get(secondary_value, 0) + 1

    return eligible.loc[selected_rows].copy()
