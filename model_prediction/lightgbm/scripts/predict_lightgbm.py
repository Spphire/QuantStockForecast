#!/usr/bin/env python3
"""Run zero-shot LightGBM inference on a normalized stock dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from data_module.common.stock_schema import normalize_dataframe
from model_prediction.lightgbm.scripts.train_lightgbm import (
    add_targets,
    classification_metrics,
    engineer_features,
    ranking_metrics,
    regression_metrics,
    select_feature_columns,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate zero-shot predictions from an existing LightGBM model."
    )
    parser.add_argument("input_csv", help="Normalized CSV path produced by a fetcher.")
    parser.add_argument("--model-path", required=True, help="Path to model.txt produced by LightGBM.")
    parser.add_argument(
        "--reference-metrics",
        required=True,
        help="metrics.json from the original training run, used to infer mode, horizon, and feature list.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory used to store zero-shot predictions and summary files.",
    )
    parser.add_argument(
        "--eval-start",
        default="",
        help="Optional inclusive start date for the evaluation slice.",
    )
    parser.add_argument(
        "--eval-end",
        default="",
        help="Optional inclusive end date for the evaluation slice.",
    )
    return parser.parse_args()


def output_dir_for(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    input_stem = Path(args.input_csv).stem
    return PROJECT_ROOT / "model_prediction" / "lightgbm" / "artifacts" / f"{input_stem}_zeroshot"


def filter_eval_period(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    working = df.copy()
    if start:
        working = working[working["date"] >= pd.to_datetime(start)].copy()
    if end:
        working = working[working["date"] <= pd.to_datetime(end)].copy()
    return working


def neutral_feature_fill_value(column: str) -> float:
    if column.startswith("cs_rank_") or "price_position" in column:
        return 0.5
    return 0.0


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_csv)
    model_path = Path(args.model_path)
    metrics_path = Path(args.reference_metrics)
    output_dir = output_dir_for(args)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        return 1
    if not model_path.exists():
        print(f"[ERROR] Model not found: {model_path}")
        return 1
    if not metrics_path.exists():
        print(f"[ERROR] Reference metrics not found: {metrics_path}")
        return 1

    try:
        import lightgbm as lgb
    except ModuleNotFoundError as exc:
        print(f"[ERROR] lightgbm is required for prediction: {exc}")
        return 1

    reference = json.loads(metrics_path.read_text(encoding="utf-8"))
    mode = str(reference["mode"])
    horizon = int(reference["horizon"])
    threshold = float(reference.get("threshold", 0.0))
    feature_columns = list(reference["feature_columns"])
    filled_missing_features: dict[str, float] = {}

    try:
        raw_df = pd.read_csv(input_path, encoding="utf-8-sig")
        normalized_df = normalize_dataframe(raw_df)
        feature_df = engineer_features(normalized_df)
        feature_df, target_column, target_return_column = add_targets(
            feature_df, mode, horizon, threshold
        )
        feature_df = filter_eval_period(feature_df, args.eval_start, args.eval_end)
        available_features = select_feature_columns(feature_df)
        missing_features = [column for column in feature_columns if column not in available_features]
        for column in missing_features:
            fill_value = neutral_feature_fill_value(column)
            feature_df[column] = fill_value
            filled_missing_features[column] = fill_value

        prepared_df = feature_df.dropna(subset=feature_columns).copy()
        if prepared_df.empty:
            raise ValueError("No rows remain after feature engineering and evaluation filtering.")
    except Exception as exc:
        print(f"[ERROR] Failed to prepare zero-shot dataset: {exc}")
        return 1

    booster = lgb.Booster(model_str=model_path.read_text(encoding="utf-8"))
    scores = booster.predict(prepared_df[feature_columns].to_numpy())

    prediction_columns = ["date", "symbol", "close"]
    for optional_column in ["amount", "turnover", "volume"]:
        if optional_column in prepared_df.columns:
            prediction_columns.append(optional_column)
    prediction_columns.append(target_return_column)
    if target_column != target_return_column:
        prediction_columns.append(target_column)

    predictions = prepared_df[prediction_columns].copy()
    if mode == "classification":
        predictions["pred_probability"] = scores
        predictions["pred_label"] = (predictions["pred_probability"] >= 0.5).astype(int)
        metrics_df = predictions.dropna(subset=[target_column]).copy()
        metrics = (
            classification_metrics(
                metrics_df[target_column].to_numpy().astype(int),
                metrics_df["pred_probability"].to_numpy(),
            )
            if not metrics_df.empty
            else {}
        )
    elif mode == "ranking":
        predictions["pred_score"] = scores
        predictions["pred_rank"] = (
            predictions.groupby("date")["pred_score"].rank(ascending=False, method="first")
        )
        metrics_df = predictions.dropna(subset=[target_column, target_return_column]).copy()
        metrics = (
            ranking_metrics(
                metrics_df[target_column].to_numpy(),
                metrics_df["pred_score"].to_numpy(),
                metrics_df[target_return_column].to_numpy(),
            )
            if not metrics_df.empty
            else {}
        )
    else:
        predictions["pred_return"] = scores
        metrics_df = predictions.dropna(subset=[target_column]).copy()
        metrics = (
            regression_metrics(
                metrics_df[target_column].to_numpy(),
                metrics_df["pred_return"].to_numpy(),
            )
            if not metrics_df.empty
            else {}
        )

    prepared_to_save = prepared_df.copy()
    prepared_to_save["date"] = prepared_to_save["date"].dt.strftime("%Y-%m-%d")
    prepared_to_save.to_csv(output_dir / "prepared_dataset.csv", index=False, encoding="utf-8")

    predictions_to_save = predictions.copy()
    predictions_to_save["date"] = pd.to_datetime(predictions_to_save["date"]).dt.strftime("%Y-%m-%d")
    predictions_to_save.to_csv(output_dir / "test_predictions.csv", index=False, encoding="utf-8")

    summary = {
        "input_csv": str(input_path),
        "model_path": str(model_path),
        "reference_metrics": str(metrics_path),
        "mode": mode,
        "horizon": horizon,
        "threshold": threshold,
        "feature_columns": feature_columns,
        "rows": int(len(predictions_to_save)),
        "metrics_rows": int(len(metrics_df)) if "metrics_df" in locals() else 0,
        "symbol_count": int(predictions_to_save["symbol"].nunique()),
        "date_min": predictions_to_save["date"].min() if not predictions_to_save.empty else None,
        "date_max": predictions_to_save["date"].max() if not predictions_to_save.empty else None,
        "eval_start": args.eval_start or None,
        "eval_end": args.eval_end or None,
        "filled_missing_features": filled_missing_features,
        "metrics": metrics,
    }
    (output_dir / "predict_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Prepared dataset: {output_dir / 'prepared_dataset.csv'}")
    print(f"[OK] Predictions file: {output_dir / 'test_predictions.csv'}")
    print(f"[OK] Predict summary: {output_dir / 'predict_summary.json'}")
    print(f"[INFO] Rows: {summary['rows']}")
    print(f"[INFO] Symbols: {summary['symbol_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
