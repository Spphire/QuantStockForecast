"""Signal-level guardrails applied before portfolio construction."""

from __future__ import annotations

import pandas as pd


def apply_signal_guards(
    df: pd.DataFrame,
    *,
    min_score: float = float("-inf"),
    min_confidence: float = 0.0,
    require_positive_label: bool = False,
    allowed_horizons: set[int] | None = None,
) -> pd.DataFrame:
    working = df.copy()
    working = working[working["score"] >= min_score]
    working = working[working["confidence"] >= min_confidence]

    if require_positive_label and "pred_label" in working.columns:
        working = working[working["pred_label"] == 1]

    if allowed_horizons:
        working = working[working["horizon"].isin(allowed_horizons)]

    return working.copy()
