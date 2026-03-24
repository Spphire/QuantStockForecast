#!/usr/bin/env python3
"""Train a lightweight transformer stock baseline on the shared normalized schema."""

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
    fit_feature_scaler,
    inverse_target,
    load_and_prepare_frame,
    output_dir_for,
    predict_model,
    require_torch,
    save_feature_importance,
    save_model_bundle,
    sequence_indices_for_dates,
    split_frame_by_dates,
    split_unique_dates,
    target_scaler_stats,
    train_model,
)
from model_prediction.lightgbm.scripts.train_lightgbm import (
    classification_metrics,
    ranking_metrics,
    regression_metrics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a lightweight transformer stock model or prepare an aligned modeling dataset."
    )
    parser.add_argument("input_csv", help="Normalized CSV path produced by the fetcher.")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory used to store prepared data, metrics, and model artifacts.",
    )
    parser.add_argument(
        "--mode",
        default="regression",
        choices=["classification", "regression", "ranking"],
        help="Choose binary direction prediction, regression, or rank-surrogate training.",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=5,
        help="Forecast horizon in trading days.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Positive-return threshold for classification labels.",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.7,
        help="Fraction of unique dates used for the training split.",
    )
    parser.add_argument(
        "--valid-ratio",
        type=float,
        default=0.15,
        help="Fraction of unique dates used for the validation split.",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=20,
        help="Number of trading days used per sequence window.",
    )
    parser.add_argument(
        "--hidden-dim",
        type=int,
        default=64,
        help="Transformer hidden dimension.",
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=2,
        help="Number of Transformer encoder layers.",
    )
    parser.add_argument(
        "--num-heads",
        type=int,
        default=4,
        help="Number of attention heads.",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.1,
        help="Transformer dropout rate.",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=1e-3,
        help="AdamW learning rate.",
    )
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=1e-4,
        help="AdamW weight decay.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Training batch size.",
    )
    parser.add_argument(
        "--max-epochs",
        type=int,
        default=30,
        help="Maximum training epochs.",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=5,
        help="Early stopping patience on validation loss.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="Torch device name. Use auto, cpu, or cuda.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Prepare features and targets without fitting a transformer.",
    )
    return parser.parse_args()


def prediction_columns(test_df: pd.DataFrame, target_return_column: str, target_column: str) -> list[str]:
    columns = ["date", "symbol", "close"]
    for optional_column in ["amount", "turnover", "volume"]:
        if optional_column in test_df.columns:
            columns.append(optional_column)
    columns.append(target_return_column)
    if target_column != target_return_column:
        columns.append(target_column)
    return columns


def main() -> int:
    args = parse_args()
    output_dir = output_dir_for(args.input_csv, args.mode, args.horizon, args.lookback, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input_csv)
    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        return 1

    try:
        prepared_df, target_column, target_return_column, feature_columns, filled_missing_features = load_and_prepare_frame(
            input_path,
            mode=args.mode,
            horizon=args.horizon,
            threshold=args.threshold,
            require_target=True,
        )
        train_dates, valid_dates, test_dates, split_summary = split_unique_dates(
            prepared_df, args.train_ratio, args.valid_ratio, label_horizon=args.horizon
        )
        train_df, valid_df, test_df = split_frame_by_dates(prepared_df, train_dates, valid_dates, test_dates)
        feature_stats = fit_feature_scaler(train_df, feature_columns)
        scaled_df = apply_feature_scaler(prepared_df, feature_columns, feature_stats)
        target_stats = target_scaler_stats(train_df, target_column, args.mode)
        sequences, sample_meta, sample_targets, sample_target_returns = build_sequence_samples(
            scaled_df,
            feature_columns,
            target_column,
            target_return_column,
            args.lookback,
            mode=args.mode,
            target_stats=target_stats,
            include_missing_target=False,
        )

        sample_train_idx = sequence_indices_for_dates(sample_meta, train_dates)
        sample_valid_idx = sequence_indices_for_dates(sample_meta, valid_dates)
        sample_test_idx = sequence_indices_for_dates(sample_meta, test_dates)
        if len(sample_train_idx) == 0 or len(sample_valid_idx) == 0 or len(sample_test_idx) == 0:
            raise ValueError("Transformer split produced an empty train/valid/test set. Reduce lookback or extend the date range.")
    except Exception as exc:
        print(f"[ERROR] Failed to prepare transformer data: {exc}")
        return 1

    prepared_to_save = prepared_df.copy()
    prepared_to_save["date"] = prepared_to_save["date"].dt.strftime("%Y-%m-%d")
    prepared_path = output_dir / "prepared_dataset.csv"
    prepared_to_save.to_csv(prepared_path, index=False, encoding="utf-8")

    summary = {
        "input_csv": str(input_path),
        "prepared_csv": str(prepared_path),
        "mode": args.mode,
        "horizon": args.horizon,
        "lookback": args.lookback,
        "threshold": args.threshold,
        "symbol_count": int(prepared_df["symbol"].nunique()),
        "feature_columns": feature_columns,
        "target_column": target_column,
        "target_return_column": target_return_column,
        "split_summary": split_summary,
        "filled_missing_features": filled_missing_features,
    }

    if args.prepare_only:
        (output_dir / "prepare_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[OK] Prepared dataset: {prepared_path}")
        print(f"[INFO] Feature count: {len(feature_columns)}")
        print(f"[INFO] Target column: {target_column}")
        return 0

    try:
        require_torch()
    except ModuleNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 1

    train_sequences = sequences[sample_train_idx]
    valid_sequences = sequences[sample_valid_idx]
    test_sequences = sequences[sample_test_idx]
    train_targets = sample_targets[sample_train_idx]
    valid_targets = sample_targets[sample_valid_idx]
    test_targets = sample_targets[sample_test_idx]

    if args.mode == "classification":
        train_targets = train_targets.astype(np.float32)
        valid_targets = valid_targets.astype(np.float32)
        test_targets = test_targets.astype(np.float32)
    elif args.mode == "ranking":
        train_targets = train_targets.astype(np.float32)
        valid_targets = valid_targets.astype(np.float32)
        test_targets = test_targets.astype(np.float32)

    try:
        model, train_summary, runtime = train_model(
            train_sequences=train_sequences,
            train_targets=train_targets,
            valid_sequences=valid_sequences,
            valid_targets=valid_targets,
            feature_dim=len(feature_columns),
            lookback=args.lookback,
            hidden_dim=args.hidden_dim,
            num_layers=args.num_layers,
            num_heads=args.num_heads,
            dropout=args.dropout,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            batch_size=args.batch_size,
            max_epochs=args.max_epochs,
            patience=args.patience,
            mode=args.mode,
            device_name=args.device,
        )
    except Exception as exc:
        print(f"[ERROR] Training failed: {exc}")
        return 1

    test_scores = predict_model(model, test_sequences, batch_size=args.batch_size, device_name=args.device)
    test_meta = sample_meta.iloc[sample_test_idx].copy().reset_index(drop=True)
    prediction_df = test_meta[prediction_columns(test_meta, target_return_column, target_column)].copy()

    if args.mode == "classification":
        probabilities = 1.0 / (1.0 + np.exp(-test_scores))
        prediction_df["pred_probability"] = probabilities
        prediction_df["pred_label"] = (probabilities >= 0.5).astype(int)
        metrics = classification_metrics(
            test_meta[target_column].to_numpy().astype(int),
            prediction_df["pred_probability"].to_numpy(),
        )
    elif args.mode == "ranking":
        prediction_df["pred_score"] = test_scores
        prediction_df["pred_rank"] = (
            prediction_df.groupby("date")["pred_score"].rank(ascending=False, method="first")
        )
        metrics = ranking_metrics(
            test_meta[target_column].to_numpy(),
            prediction_df["pred_score"].to_numpy(),
            test_meta[target_return_column].to_numpy(),
        )
    else:
        predictions = inverse_target(test_scores, mode=args.mode, target_stats=target_stats)
        prediction_df["pred_return"] = predictions
        metrics = regression_metrics(
            test_meta[target_column].to_numpy(),
            prediction_df["pred_return"].to_numpy(),
        )

    prediction_df["date"] = pd.to_datetime(prediction_df["date"]).dt.strftime("%Y-%m-%d")
    prediction_path = output_dir / "test_predictions.csv"
    prediction_df.to_csv(prediction_path, index=False, encoding="utf-8")

    model_metadata = {
        "mode": args.mode,
        "horizon": args.horizon,
        "lookback": args.lookback,
        "hidden_dim": args.hidden_dim,
        "num_layers": args.num_layers,
        "num_heads": args.num_heads,
        "dropout": args.dropout,
        "feature_stats_path": str(output_dir / "feature_stats.json"),
        "target_stats": target_stats,
    }
    model_path, metadata_path, feature_stats_path = save_model_bundle(
        model=model,
        output_dir=output_dir,
        metadata=model_metadata,
        feature_stats=feature_stats,
    )
    feature_importance_path = save_feature_importance(model, feature_columns, output_dir)

    metrics["best_epoch"] = int(train_summary["best_epoch"])
    metrics["best_val_loss"] = float(train_summary["best_val_loss"])
    metrics["final_train_loss"] = float(train_summary["final_train_loss"])
    metrics["final_valid_loss"] = float(train_summary["final_valid_loss"])
    metrics["device"] = train_summary["device"]
    metrics["model_path"] = str(model_path)
    metrics["model_metadata_path"] = str(metadata_path)
    metrics["feature_stats_path"] = str(feature_stats_path)
    metrics["feature_importance_path"] = str(feature_importance_path)

    full_summary = summary | {"metrics": metrics}
    (output_dir / "metrics.json").write_text(
        json.dumps(full_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Prepared dataset: {prepared_path}")
    print(f"[OK] Metrics file: {output_dir / 'metrics.json'}")
    print(f"[OK] Predictions file: {prediction_path}")
    print(f"[OK] Model file: {model_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
