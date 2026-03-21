#!/usr/bin/env python3
"""Run zero-shot XGBoost inference on a normalized stock dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_prediction.common.compatible_experts import (
    add_xgboost_style_features,
    ensure_feature_columns,
    neutral_fill_value,
    prepare_base_frame,
)
from model_prediction.lightgbm.scripts.train_lightgbm import (
    classification_metrics,
    ranking_metrics,
    regression_metrics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate zero-shot predictions from an existing XGBoost model."
    )
    parser.add_argument("input_csv", help="Normalized CSV path produced by a fetcher.")
    parser.add_argument("--model-path", required=True, help="Path to model.json produced by XGBoost.")
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
    parser.add_argument("--eval-start", default="", help="Optional inclusive start date.")
    parser.add_argument("--eval-end", default="", help="Optional inclusive end date.")
    return parser.parse_args()


def output_dir_for(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    input_stem = Path(args.input_csv).stem
    return PROJECT_ROOT / "model_prediction" / "xgboost" / "artifacts" / f"{input_stem}_zeroshot"


def filter_eval_period(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    working = df.copy()
    if start:
        working = working[working["date"] >= pd.to_datetime(start)].copy()
    if end:
        working = working[working["date"] <= pd.to_datetime(end)].copy()
    return working


def base_prediction_columns(
    df: pd.DataFrame,
    target_return_column: str,
    target_column: str,
) -> list[str]:
    columns = ["date", "symbol", "close"]
    for optional_column in ["amount", "turnover", "volume"]:
        if optional_column in df.columns:
            columns.append(optional_column)
    columns.append(target_return_column)
    if target_column != target_return_column:
        columns.append(target_column)
    return columns


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
        import xgboost as xgb
    except ModuleNotFoundError as exc:
        print(f"[ERROR] xgboost is required for prediction: {exc}")
        return 1

    reference = json.loads(metrics_path.read_text(encoding="utf-8"))
    mode = str(reference["mode"])
    horizon = int(reference["horizon"])
    threshold = float(reference.get("threshold", 0.0))
    feature_columns = list(reference["feature_columns"])

    try:
        feature_df, target_column, target_return_column = prepare_base_frame(
            input_path,
            mode=mode,
            horizon=horizon,
            threshold=threshold,
        )
        feature_df, _ = add_xgboost_style_features(feature_df)
        feature_df = filter_eval_period(feature_df, args.eval_start, args.eval_end)
        feature_df = ensure_feature_columns(feature_df, feature_columns)
        prepared_df = feature_df.dropna(subset=feature_columns).copy()
        if prepared_df.empty:
            raise ValueError("No rows remain after feature engineering and evaluation filtering.")
    except Exception as exc:
        print(f"[ERROR] Failed to prepare zero-shot dataset: {exc}")
        return 1

    booster = xgb.Booster()
    booster.load_model(str(model_path))
    matrix = xgb.DMatrix(prepared_df[feature_columns], feature_names=feature_columns)

    best_iteration = int(reference.get("metrics", {}).get("best_iteration", 0) or 0)
    if best_iteration > 0:
        scores = booster.predict(matrix, iteration_range=(0, best_iteration))
    else:
        scores = booster.predict(matrix)

    predictions = prepared_df[base_prediction_columns(prepared_df, target_return_column, target_column)].copy()
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
        predictions["pred_rank"] = predictions.groupby("date")["pred_score"].rank(
            ascending=False, method="first"
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
    prepared_to_save["date"] = pd.to_datetime(prepared_to_save["date"]).dt.strftime("%Y-%m-%d")
    prepared_path = output_dir / "prepared_dataset.csv"
    prepared_to_save.to_csv(prepared_path, index=False, encoding="utf-8")

    predictions_to_save = predictions.copy()
    predictions_to_save["date"] = pd.to_datetime(predictions_to_save["date"]).dt.strftime("%Y-%m-%d")
    predictions_path = output_dir / "test_predictions.csv"
    predictions_to_save.to_csv(predictions_path, index=False, encoding="utf-8")

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
        "filled_missing_features": {
            column: neutral_fill_value(column)
            for column in feature_columns
            if column not in feature_df.columns
        },
        "metrics": metrics,
        "expert_name": "xgboost",
    }
    summary_path = output_dir / "predict_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Prepared dataset: {prepared_path}")
    print(f"[OK] Predictions file: {predictions_path}")
    print(f"[OK] Predict summary: {summary_path}")
    print(f"[INFO] Rows: {summary['rows']}")
    print(f"[INFO] Symbols: {summary['symbol_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
