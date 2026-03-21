"""Shared utilities for combining multiple expert prediction files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from model_prediction.common.signal_interface import load_signal_frame


SUPPORTED_METHODS = ["mean_score", "rank_average", "vote"]
KNOWN_EXPERT_NAMES = ["lightgbm", "xgboost", "catboost", "lstm", "transformer", "ensemble"]
GENERIC_MODEL_NAMES = {"predict", "prediction", "zeroshot", "zero_shot", "train", "unknown", "unknown_model"}


def output_dir_for(project_root: Path, args: Any) -> Path:
    if getattr(args, "output_dir", ""):
        return Path(args.output_dir)
    method = str(getattr(args, "method", "rank_average"))
    model_name = str(getattr(args, "model_name", "")).strip() or "ensemble"
    return project_root / "model_prediction" / "ensemble" / "artifacts" / method / model_name


def parse_weights(raw_weights: list[str], expert_names: list[str]) -> dict[str, float]:
    if not raw_weights:
        return {name: 1.0 for name in expert_names}

    if len(raw_weights) != len(expert_names):
        raise ValueError(
            f"Expected {len(expert_names)} weights for experts {expert_names}, got {len(raw_weights)}."
        )
    weights = {name: float(value) for name, value in zip(expert_names, raw_weights, strict=True)}
    if all(abs(value) <= 1e-12 for value in weights.values()):
        raise ValueError("At least one ensemble weight must be non-zero.")
    return weights


def default_manifest_path(output_dir: Path) -> Path:
    return output_dir / "ensemble_manifest.json"


def load_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_manifest(path: str | Path, payload: dict[str, Any]) -> Path:
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def infer_expert_name(path: str | Path, fallback: str) -> str:
    normalized = str(fallback).strip().lower()
    if normalized and normalized not in GENERIC_MODEL_NAMES:
        return normalized

    parts = [part.lower() for part in Path(path).parts]
    for candidate in KNOWN_EXPERT_NAMES:
        if candidate in parts:
            return candidate
    return normalized or Path(path).stem.lower()


def load_expert_frames(
    prediction_csvs: list[str],
    *,
    min_experts: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if not prediction_csvs:
        raise ValueError("At least one --prediction-csv is required.")

    expert_frames: list[pd.DataFrame] = []
    metadata: list[dict[str, Any]] = []
    for prediction_csv in prediction_csvs:
        signal_df = load_signal_frame(prediction_csv)
        raw_model_name = str(signal_df["model_name"].iloc[0]) if not signal_df.empty else Path(prediction_csv).stem
        model_name = infer_expert_name(prediction_csv, raw_model_name)
        model_mode = str(signal_df["model_mode"].iloc[0]) if not signal_df.empty else "unknown"

        expert_frame = signal_df[
            ["date", "symbol", "score", "confidence", "horizon", "model_mode", "realized_return"]
        ].copy()
        for optional in ["close", "amount", "turnover", "volume", "pred_label", "pred_rank"]:
            if optional in signal_df.columns:
                expert_frame[optional] = signal_df[optional]
        expert_frame = expert_frame.rename(
            columns={
                "score": f"score__{model_name}",
                "confidence": f"confidence__{model_name}",
                "model_mode": f"model_mode__{model_name}",
            }
        )
        expert_frames.append(expert_frame)
        metadata.append(
            {
                "model_name": model_name,
                "model_mode": model_mode,
                "prediction_csv": str(Path(prediction_csv).resolve()),
                "rows": int(len(expert_frame)),
            }
        )

    key_columns = ["date", "symbol", "horizon"]
    base_columns = ["realized_return", "close", "amount", "turnover", "volume", "pred_label", "pred_rank"]

    def _coalesce_frame(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
        merged_frame = left.merge(
            right,
            on=key_columns,
            how="outer",
            suffixes=("", "__rhs"),
        )
        for column in base_columns:
            rhs_column = f"{column}__rhs"
            if column in merged_frame.columns and rhs_column in merged_frame.columns:
                merged_frame[column] = merged_frame[column].combine_first(merged_frame[rhs_column])
                merged_frame = merged_frame.drop(columns=[rhs_column])
        return merged_frame

    merged = expert_frames[0]
    for frame in expert_frames[1:]:
        merged = _coalesce_frame(merged, frame)

    score_columns = [column for column in merged.columns if column.startswith("score__")]
    if not score_columns:
        raise ValueError("No score columns were available after merging expert predictions.")
    merged["available_expert_count"] = merged[score_columns].notna().sum(axis=1)
    merged = merged[merged["available_expert_count"] >= min_experts].copy()
    if merged.empty:
        raise ValueError(
            f"No rows remain after requiring at least {min_experts} expert predictions per row."
        )
    return merged.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True), metadata


def per_date_zscore(values: pd.Series, dates: pd.Series) -> pd.Series:
    working = pd.to_numeric(values, errors="coerce")
    grouped = working.groupby(dates)
    means = grouped.transform("mean")
    stds = grouped.transform("std").replace(0.0, np.nan)
    zscore = (working - means) / stds
    return zscore.fillna(0.0)


def per_date_rank(values: pd.Series, dates: pd.Series) -> pd.Series:
    working = pd.to_numeric(values, errors="coerce")
    return working.groupby(dates).rank(pct=True, method="average")


def vote_signal(values: pd.Series, dates: pd.Series, model_mode: str) -> pd.Series:
    working = pd.to_numeric(values, errors="coerce")
    normalized_mode = str(model_mode).lower()
    if normalized_mode == "classification":
        return (working >= 0.5).astype(float)
    if normalized_mode == "regression":
        return (working >= 0.0).astype(float)
    ranks = per_date_rank(working, dates)
    return (ranks >= 0.5).astype(float)


def combine_predictions(
    merged_df: pd.DataFrame,
    *,
    method: str,
    weights: dict[str, float],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported ensemble method: {method}")

    working = merged_df.copy()
    dates = working["date"]
    model_names = [column.split("__", 1)[1] for column in working.columns if column.startswith("score__")]

    normalized_scores: dict[str, pd.Series] = {}
    normalized_confidences: dict[str, pd.Series] = {}
    for model_name in model_names:
        score_column = f"score__{model_name}"
        confidence_column = f"confidence__{model_name}"
        model_mode = str(working.get(f"model_mode__{model_name}", pd.Series(dtype=object)).dropna().iloc[0]) if f"model_mode__{model_name}" in working.columns and not working[f"model_mode__{model_name}"].dropna().empty else "unknown"
        raw_scores = pd.to_numeric(working[score_column], errors="coerce")
        if method == "mean_score":
            normalized_scores[model_name] = per_date_zscore(raw_scores, dates)
        elif method == "rank_average":
            normalized_scores[model_name] = per_date_rank(raw_scores, dates).fillna(0.5)
        else:
            normalized_scores[model_name] = vote_signal(raw_scores, dates, model_mode)

        if confidence_column in working.columns:
            normalized_confidences[model_name] = pd.to_numeric(working[confidence_column], errors="coerce").fillna(0.0)
        else:
            normalized_confidences[model_name] = per_date_rank(raw_scores, dates).fillna(0.0)

    weight_vector = pd.DataFrame(
        {
            model_name: float(weights.get(model_name, 1.0))
            for model_name in model_names
        },
        index=working.index,
    )
    score_frame = pd.DataFrame(normalized_scores)
    confidence_frame = pd.DataFrame(normalized_confidences)
    availability = score_frame.notna().astype(float)
    effective_weights = weight_vector * availability
    weight_sums = effective_weights.sum(axis=1).replace(0.0, np.nan)

    combined_score = (score_frame.fillna(0.0) * effective_weights).sum(axis=1) / weight_sums
    combined_confidence = (confidence_frame.fillna(0.0) * effective_weights).sum(axis=1) / weight_sums

    if method == "vote":
        combined_score = combined_score.clip(0.0, 1.0)

    horizon = int(pd.to_numeric(working["horizon"], errors="coerce").dropna().iloc[0]) if not working.empty else 1
    target_return_column = f"target_return_{horizon}d"
    output = pd.DataFrame(
        {
            "date": working["date"],
            "symbol": working["symbol"],
            "close": working["close"] if "close" in working.columns else np.nan,
            "horizon": working["horizon"],
            target_return_column: working["realized_return"],
            "pred_score": combined_score.fillna(0.0),
            "ensemble_confidence": combined_confidence.fillna(0.0),
            "available_expert_count": working["available_expert_count"],
        }
    )
    for optional in ["amount", "turnover", "volume"]:
        if optional in working.columns:
            output[optional] = working[optional]
    output["pred_rank"] = output.groupby("date")["pred_score"].rank(ascending=False, method="first")

    summary = {
        "method": method,
        "row_count": int(len(output)),
        "symbol_count": int(output["symbol"].nunique()),
        "date_min": output["date"].min().strftime("%Y-%m-%d") if not output.empty else None,
        "date_max": output["date"].max().strftime("%Y-%m-%d") if not output.empty else None,
        "horizon": horizon,
        "target_return_column": target_return_column,
        "expert_names": model_names,
        "weights": {name: float(weights.get(name, 1.0)) for name in model_names},
        "min_available_experts": int(output["available_expert_count"].min()) if not output.empty else 0,
        "mean_available_experts": float(output["available_expert_count"].mean()) if not output.empty else 0.0,
    }
    return output.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True), summary
