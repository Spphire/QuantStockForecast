#!/usr/bin/env python3
"""Run zero-shot inference with a trained transformer stock model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_prediction.transformer.core import (
    apply_feature_scaler,
    build_sequence_samples,
    inverse_target,
    load_and_prepare_frame,
    load_model_bundle,
    predict_model,
    require_torch,
    output_dir_for,
)
from model_prediction.lightgbm.scripts.train_lightgbm import (
    classification_metrics,
    ranking_metrics,
    regression_metrics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate zero-shot predictions from a trained transformer model."
    )
    parser.add_argument("input_csv", help="Normalized CSV path produced by a fetcher.")
    parser.add_argument("--model-path", required=True, help="Path to model.pt produced by training.")
    parser.add_argument(
        "--reference-metrics",
        required=True,
        help="metrics.json from the original training run, used to infer mode, horizon, lookback, and feature list.",
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


def output_prediction_columns(df: pd.DataFrame, target_return_column: str, target_column: str) -> list[str]:
    columns = ["date", "symbol", "close"]
    for optional_column in ["amount", "turnover", "volume"]:
        if optional_column in df.columns:
            columns.append(optional_column)
    columns.append(target_return_column)
    if target_column != target_return_column:
        columns.append(target_column)
    return columns


def resolve_model_paths(model_arg: str, metrics_reference: dict[str, object], output_dir: Path) -> tuple[Path, Path, Path]:
    model_path = Path(model_arg)
    if model_path.is_dir():
        model_path = model_path / "model.pt"
    metadata_ref = str(metrics_reference.get("model_metadata_path", "")).strip()
    metadata_path = Path(metadata_ref) if metadata_ref else output_dir / "model_metadata.json"
    if not metadata_path.exists():
        fallback = model_path.with_name("model_metadata.json")
        if fallback.exists():
            metadata_path = fallback
    feature_stats_ref = str(metrics_reference.get("feature_stats_path", "")).strip()
    feature_stats_path = Path(feature_stats_ref) if feature_stats_ref else output_dir / "feature_stats.json"
    if not feature_stats_path.exists():
        fallback = model_path.with_name("feature_stats.json")
        if fallback.exists():
            feature_stats_path = fallback
    return model_path, metadata_path, feature_stats_path


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_csv)
    metrics_path = Path(args.reference_metrics)
    output_dir = output_dir_for(input_path, "transformer", 1, 1, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        return 1
    if not metrics_path.exists():
        print(f"[ERROR] Reference metrics not found: {metrics_path}")
        return 1

    try:
        reference = json.loads(metrics_path.read_text(encoding="utf-8"))
        metrics_block = dict(reference.get("metrics", {}))
        mode = str(reference["mode"])
        horizon = int(reference["horizon"])
        lookback = int(reference.get("lookback", 20))
        threshold = float(reference.get("threshold", 0.0))
        feature_columns = list(reference["feature_columns"])
        target_column = str(reference["target_column"])
        target_return_column = str(reference["target_return_column"])
        output_dir = output_dir_for(input_path, mode, horizon, lookback, args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"[ERROR] Failed to parse reference metrics: {exc}")
        return 1

    model_path, metadata_path, feature_stats_path = resolve_model_paths(args.model_path, metrics_block, output_dir)
    if not model_path.exists():
        print(f"[ERROR] Model not found: {model_path}")
        return 1
    if not metadata_path.exists():
        print(f"[ERROR] Model metadata not found: {metadata_path}")
        return 1
    if not feature_stats_path.exists():
        print(f"[ERROR] Feature stats not found: {feature_stats_path}")
        return 1

    try:
        prepared_df, _, _, _, filled_missing_features = load_and_prepare_frame(
            input_path,
            mode=mode,
            horizon=horizon,
            threshold=threshold,
            eval_start=args.eval_start,
            eval_end=args.eval_end,
            reference_feature_columns=feature_columns,
            require_target=False,
        )
        prepared_to_save = prepared_df.copy()
        prepared_to_save["date"] = prepared_to_save["date"].dt.strftime("%Y-%m-%d")
        prepared_to_save.to_csv(output_dir / "prepared_dataset.csv", index=False, encoding="utf-8")
        feature_stats = json.loads(feature_stats_path.read_text(encoding="utf-8"))
        target_stats = dict(json.loads(metadata_path.read_text(encoding="utf-8")).get("target_stats", {}))
        scaled_df = apply_feature_scaler(prepared_df, feature_columns, feature_stats)
        sequences, sample_meta, sample_targets, sample_target_returns = build_sequence_samples(
            scaled_df,
            feature_columns,
            target_column,
            target_return_column,
            lookback,
            mode=mode,
            target_stats=target_stats,
            include_missing_target=True,
        )
    except Exception as exc:
        print(f"[ERROR] Failed to prepare zero-shot transformer dataset: {exc}")
        return 1

    try:
        require_torch()
        model, metadata = load_model_bundle(
            model_path=model_path,
            metadata_path=metadata_path,
            feature_dim=len(feature_columns),
            lookback=lookback,
        )
    except Exception as exc:
        print(f"[ERROR] Failed to load transformer model: {exc}")
        return 1

    scores = predict_model(model, sequences, batch_size=256)
    predictions = sample_meta[output_prediction_columns(sample_meta, target_return_column, target_column)].copy()
    if mode == "classification":
        probabilities = 1.0 / (1.0 + np.exp(-scores))
        predictions["pred_probability"] = probabilities
        predictions["pred_label"] = (probabilities >= 0.5).astype(int)
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
        predictions["pred_return"] = inverse_target(scores, mode=mode, target_stats=target_stats)
        metrics_df = predictions.dropna(subset=[target_column]).copy()
        metrics = (
            regression_metrics(
                metrics_df[target_column].to_numpy(),
                metrics_df["pred_return"].to_numpy(),
            )
            if not metrics_df.empty
            else {}
        )

    predictions["date"] = pd.to_datetime(predictions["date"]).dt.strftime("%Y-%m-%d")
    predictions_path = output_dir / "test_predictions.csv"
    predictions.to_csv(predictions_path, index=False, encoding="utf-8")

    summary = {
        "input_csv": str(input_path),
        "model_path": str(model_path),
        "reference_metrics": str(metrics_path),
        "model_metadata_path": str(metadata_path),
        "feature_stats_path": str(feature_stats_path),
        "mode": mode,
        "horizon": horizon,
        "lookback": lookback,
        "threshold": threshold,
        "feature_columns": feature_columns,
        "rows": int(len(predictions)),
        "metrics_rows": int(len(metrics_df)) if "metrics_df" in locals() else 0,
        "symbol_count": int(predictions["symbol"].nunique()),
        "date_min": predictions["date"].min() if not predictions.empty else None,
        "date_max": predictions["date"].max() if not predictions.empty else None,
        "eval_start": args.eval_start or None,
        "eval_end": args.eval_end or None,
        "filled_missing_features": filled_missing_features,
        "metrics": metrics,
    }
    (output_dir / "predict_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Predictions file: {predictions_path}")
    print(f"[OK] Predict summary: {output_dir / 'predict_summary.json'}")
    print(f"[INFO] Rows: {summary['rows']}")
    print(f"[INFO] Symbols: {summary['symbol_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
