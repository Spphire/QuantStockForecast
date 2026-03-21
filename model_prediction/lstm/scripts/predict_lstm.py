#!/usr/bin/env python3
"""Run PyTorch LSTM inference on a normalized stock dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_prediction.lstm.core import (  # noqa: E402
    FeatureNormalizer,
    add_targets,
    build_sequence_samples,
    classification_metrics,
    engineer_features,
    load_checkpoint,
    regression_metrics,
    run_model_in_batches,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate predictions from a trained LSTM stock model."
    )
    parser.add_argument("input_csv", help="Normalized CSV path produced by a fetcher.")
    parser.add_argument(
        "--model-path",
        required=True,
        help="Path to model.pt produced by training.",
    )
    parser.add_argument(
        "--reference-metrics",
        required=True,
        help="metrics.json from the original training run, used to infer mode, horizon, and features.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory used to store predictions and summary files.",
    )
    parser.add_argument("--eval-start", default="", help="Optional inclusive start date.")
    parser.add_argument("--eval-end", default="", help="Optional inclusive end date.")
    parser.add_argument("--device", default="", help="Torch device override.")
    return parser.parse_args()


def output_dir_for(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    input_stem = Path(args.input_csv).stem
    return PROJECT_ROOT / "model_prediction" / "lstm" / "artifacts" / f"{input_stem}_predict"


def filter_eval_period(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    working = df.copy()
    if start:
        working = working[working["date"] >= pd.to_datetime(start)].copy()
    if end:
        working = working[working["date"] <= pd.to_datetime(end)].copy()
    return working


def resolve_device(requested: str) -> str:
    if requested:
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


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
        reference = json.loads(metrics_path.read_text(encoding="utf-8"))
        checkpoint = load_checkpoint(model_path)
        config = checkpoint.get("config") if isinstance(checkpoint.get("config"), dict) else reference.get("config", {})
        if not isinstance(config, dict) or not config:
            raise ValueError("Could not recover model config from checkpoint or metrics.")
        mode = str(config["mode"])
        horizon = int(config["horizon"])
        threshold = float(config.get("threshold", 0.0))
        seq_len = int(config["seq_len"])
        feature_columns = list(checkpoint.get("feature_columns") or reference["feature_columns"])
        target_column = str(checkpoint.get("target_column") or reference["target_column"])
        target_return_column = str(
            checkpoint.get("target_return_column") or reference["target_return_column"]
        )
        normalizer_payload = checkpoint.get("normalizer") or reference.get("normalizer")
        if not isinstance(normalizer_payload, dict):
            raise ValueError("Normalizer payload missing from checkpoint.")
        normalizer = FeatureNormalizer.from_dict(normalizer_payload)
        device = resolve_device(args.device)
    except Exception as exc:
        print(f"[ERROR] Failed to load model metadata: {exc}")
        return 1

    try:
        raw_df = pd.read_csv(input_path, encoding="utf-8-sig")
        feature_df = engineer_features(raw_df)
        feature_df, inferred_target_column, inferred_target_return_column = add_targets(
            feature_df, mode, horizon, threshold
        )
        if inferred_target_column != target_column:
            target_column = inferred_target_column
        if inferred_target_return_column != target_return_column:
            target_return_column = inferred_target_return_column
        prepared_df = feature_df.dropna(subset=[target_return_column]).copy()
        prepared_df = prepared_df.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
        normalized_full = normalizer.transform(prepared_df)
        X_all, y_all, meta_all = build_sequence_samples(
            normalized_full,
            feature_columns,
            seq_len,
            target_column,
            target_return_column=target_return_column,
        )
        if len(X_all) == 0:
            raise ValueError("No sequence samples remain after feature preparation.")
    except Exception as exc:
        print(f"[ERROR] Failed to prepare prediction dataset: {exc}")
        return 1

    eval_filtered_meta = meta_all.copy()
    if args.eval_start or args.eval_end:
        mask = pd.Series(True, index=eval_filtered_meta.index)
        if args.eval_start:
            mask &= eval_filtered_meta["date"] >= pd.to_datetime(args.eval_start)
        if args.eval_end:
            mask &= eval_filtered_meta["date"] <= pd.to_datetime(args.eval_end)
        eval_filtered_meta = eval_filtered_meta[mask].copy()

    if eval_filtered_meta.empty:
        print("[ERROR] No prediction rows remain after applying the evaluation window.")
        return 1

    meta_index = meta_all.index
    eval_mask = meta_index.isin(eval_filtered_meta.index)
    X_eval = X_all[eval_mask]
    y_eval = y_all[eval_mask]
    meta_eval = meta_all[eval_mask].copy()

    model = torch.nn.Module()
    try:
        from model_prediction.lstm.core import build_lstm_model  # noqa: E402

        model = build_lstm_model(
            input_size=len(feature_columns),
            hidden_size=int(config["hidden_size"]),
            num_layers=int(config["num_layers"]),
            dropout=float(config["dropout"]),
            mode=mode,
        )
        state_dict = checkpoint.get("model_state_dict") or checkpoint.get("state_dict")
        if not isinstance(state_dict, dict):
            raise ValueError("Checkpoint does not contain model weights.")
        model.load_state_dict(state_dict)
        model = model.to(device)
    except Exception as exc:
        print(f"[ERROR] Failed to initialize model: {exc}")
        return 1

    raw_scores = run_model_in_batches(model, X_eval, batch_size=int(config["batch_size"]), device=device)
    if mode == "classification":
        scores = 1.0 / (1.0 + np.exp(-raw_scores))
    else:
        scores = raw_scores

    predictions = meta_eval.copy()
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
    if args.eval_start or args.eval_end:
        prepared_to_save = filter_eval_period(prepared_to_save, args.eval_start, args.eval_end)
    prepared_to_save["date"] = pd.to_datetime(prepared_to_save["date"]).dt.strftime("%Y-%m-%d")
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
        "seq_len": seq_len,
        "feature_columns": feature_columns,
        "rows": int(len(predictions_to_save)),
        "metrics_rows": int(len(metrics_df)) if "metrics_df" in locals() else 0,
        "symbol_count": int(predictions_to_save["symbol"].nunique()),
        "date_min": predictions_to_save["date"].min() if not predictions_to_save.empty else None,
        "date_max": predictions_to_save["date"].max() if not predictions_to_save.empty else None,
        "eval_start": args.eval_start or None,
        "eval_end": args.eval_end or None,
        "metrics": metrics,
        "expert_name": reference.get("expert_name", "lstm"),
        "config": config,
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
