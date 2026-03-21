"""Normalize model prediction outputs into a shared signal schema."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd


def standardize_symbol(value: object) -> str:
    symbol = str(value).strip().upper()
    if not symbol or symbol in {"NAN", "NONE"}:
        return ""
    compact = symbol.replace(".", "").replace("-", "")
    if compact.isdigit():
        return compact[-6:].zfill(6)
    match = re.fullmatch(r"(SH|SZ|BJ)?(\d{6})", compact)
    if match:
        return match.group(2)
    return symbol.replace(".", "-")


def infer_model_mode(df: pd.DataFrame) -> str:
    if "pred_probability" in df.columns:
        return "classification"
    if "pred_return" in df.columns:
        return "regression"
    if "pred_score" in df.columns:
        return "ranking"
    raise ValueError("Could not infer model mode from predictions file.")


def infer_score_column(df: pd.DataFrame, requested: str = "") -> str:
    if requested:
        return requested
    mode = infer_model_mode(df)
    return {
        "classification": "pred_probability",
        "regression": "pred_return",
        "ranking": "pred_score",
    }[mode]


def infer_return_column(df: pd.DataFrame) -> str:
    for column in df.columns:
        if column.startswith("target_return_"):
            return column
    raise ValueError("Could not infer forward return column from predictions file.")


def infer_horizon(df: pd.DataFrame) -> int:
    return_column = infer_return_column(df)
    match = re.search(r"target_return_(\d+)d", return_column)
    return int(match.group(1)) if match else 1


def default_model_name(predictions_csv: str | Path, requested: str = "") -> str:
    if requested:
        return requested
    path = Path(predictions_csv)
    lower_parts = [part.lower() for part in path.parts]
    for candidate in ["lightgbm", "xgboost", "catboost", "lstm", "transformer"]:
        if candidate in lower_parts:
            return candidate
    return path.parent.name or "unknown_model"


def confidence_from_score(df: pd.DataFrame, score_column: str) -> pd.Series:
    score = pd.to_numeric(df[score_column], errors="coerce")
    if score.isna().all():
        return pd.Series(0.0, index=df.index)
    return score.groupby(df["date"]).rank(pct=True, method="average").fillna(0.0)


def normalize_signals(
    df: pd.DataFrame,
    *,
    predictions_csv: str | Path = "",
    model_name: str = "",
    score_column: str = "",
) -> pd.DataFrame:
    working = df.copy()
    if "date" not in working.columns or "symbol" not in working.columns:
        raise ValueError("Predictions file must contain date and symbol columns.")

    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working["symbol"] = working["symbol"].map(standardize_symbol)

    model_mode = infer_model_mode(working)
    score_column = infer_score_column(working, score_column)
    return_column = infer_return_column(working)
    horizon = infer_horizon(working)
    model_name = default_model_name(predictions_csv, model_name)

    signal_df = pd.DataFrame(
        {
            "date": working["date"],
            "symbol": working["symbol"],
            "score": pd.to_numeric(working[score_column], errors="coerce"),
            "confidence": confidence_from_score(working, score_column),
            "horizon": horizon,
            "model_name": model_name,
            "model_mode": model_mode,
            "realized_return": pd.to_numeric(working[return_column], errors="coerce"),
        }
    )

    for column in ["close", "amount", "turnover", "volume"]:
        if column in working.columns:
            signal_df[column] = pd.to_numeric(working[column], errors="coerce")

    if "pred_label" in working.columns:
        signal_df["pred_label"] = pd.to_numeric(working["pred_label"], errors="coerce")
    if "pred_rank" in working.columns:
        signal_df["pred_rank"] = pd.to_numeric(working["pred_rank"], errors="coerce")

    signal_df = signal_df.dropna(subset=["date", "symbol", "score"]).copy()
    signal_df = signal_df.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    return signal_df


def load_signal_frame(
    predictions_csv: str | Path,
    *,
    model_name: str = "",
    score_column: str = "",
) -> pd.DataFrame:
    path = Path(predictions_csv)
    if not path.exists():
        raise FileNotFoundError(f"Predictions file not found: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    return normalize_signals(
        df,
        predictions_csv=path,
        model_name=model_name,
        score_column=score_column,
    )
