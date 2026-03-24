#!/usr/bin/env python3
"""Train a PyTorch LSTM stock baseline on the shared normalized schema."""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_prediction.lstm.core import (  # noqa: E402
    DEFAULT_SEQUENCE_COLUMNS,
    DEFAULT_SEQUENCE_WINDOW,
    PROFILE_NAME,
    FeatureNormalizer,
    add_targets,
    build_checkpoint_payload,
    build_default_config,
    build_lstm_model,
    build_sequence_samples,
    classification_metrics,
    engineer_features,
    regression_metrics,
    run_model_in_batches,
    select_feature_columns,
    set_seed,
    split_by_date,
    save_checkpoint,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a PyTorch LSTM stock model or prepare an aligned modeling dataset."
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
        choices=["regression", "classification"],
        help="Choose regression or binary direction prediction.",
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
        "--seq-len",
        type=int,
        default=DEFAULT_SEQUENCE_WINDOW,
        help="Number of trading days in each LSTM sequence.",
    )
    parser.add_argument(
        "--hidden-size",
        type=int,
        default=96,
        help="LSTM hidden state size.",
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=2,
        help="Number of stacked LSTM layers.",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.15,
        help="Dropout applied in the LSTM and head.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Mini-batch size used for training and evaluation.",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=40,
        help="Maximum number of training epochs.",
    )
    parser.add_argument("--lr", type=float, default=1e-3, help="AdamW learning rate.")
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=1e-4,
        help="AdamW weight decay.",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=8,
        help="Early stopping patience measured on validation loss.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--device",
        default="",
        help="Torch device to use. Defaults to cuda when available, otherwise cpu.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Prepare features and targets without fitting the model.",
    )
    return parser.parse_args()


def output_dir_for(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)
    input_stem = Path(args.input_csv).stem
    run_name = f"{input_stem}_{args.mode}_{args.horizon}d"
    return PROJECT_ROOT / "model_prediction" / "lstm" / "artifacts" / run_name


def resolve_device(requested: str) -> str:
    if requested:
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


def build_loader(X: np.ndarray, y: np.ndarray, batch_size: int, shuffle: bool) -> DataLoader:
    dataset = TensorDataset(
        torch.as_tensor(X, dtype=torch.float32),
        torch.as_tensor(y, dtype=torch.float32),
    )
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, drop_last=False)


def evaluate_split(
    model: torch.nn.Module,
    X: np.ndarray,
    y: np.ndarray,
    *,
    mode: str,
    batch_size: int,
    device: str,
) -> tuple[dict[str, float], np.ndarray]:
    raw_scores = run_model_in_batches(model, X, batch_size=batch_size, device=device)
    if mode == "classification":
        scores = 1.0 / (1.0 + np.exp(-raw_scores))
        metrics = classification_metrics(y.astype(int), scores)
        return metrics, scores
    metrics = regression_metrics(y, raw_scores)
    return metrics, raw_scores


def main() -> int:
    args = parse_args()
    set_seed(args.seed)
    output_dir = output_dir_for(args)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input_csv)
    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        return 1

    try:
        raw_df = pd.read_csv(input_path, encoding="utf-8-sig")
        feature_df = engineer_features(raw_df)
        feature_df, target_column, target_return_column = add_targets(
            feature_df, args.mode, args.horizon, args.threshold
        )
        feature_columns = select_feature_columns(feature_df)
        if not feature_columns:
            raise ValueError("No usable sequence features were found in the input frame.")

        prepared_df = feature_df.dropna(subset=[target_column, target_return_column]).copy()
        prepared_df = prepared_df.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
        train_df, valid_df, test_df, split_summary = split_by_date(
            prepared_df, args.train_ratio, args.valid_ratio, label_horizon=args.horizon
        )
    except Exception as exc:
        print(f"[ERROR] Failed to prepare training data: {exc}")
        return 1

    prepared_path = output_dir / "prepared_dataset.csv"
    prepared_to_save = prepared_df.copy()
    prepared_to_save["date"] = pd.to_datetime(prepared_to_save["date"]).dt.strftime("%Y-%m-%d")
    prepared_to_save.to_csv(prepared_path, index=False, encoding="utf-8")

    config = build_default_config(
        mode=args.mode,
        horizon=args.horizon,
        threshold=args.threshold,
        seq_len=args.seq_len,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
        batch_size=args.batch_size,
        epochs=args.epochs,
        lr=args.lr,
        weight_decay=args.weight_decay,
        patience=args.patience,
        seed=args.seed,
        train_ratio=args.train_ratio,
        valid_ratio=args.valid_ratio,
    )

    summary = {
        "input_csv": str(input_path),
        "prepared_csv": str(prepared_path),
        "mode": args.mode,
        "horizon": args.horizon,
        "threshold": args.threshold,
        "seq_len": args.seq_len,
        "hidden_size": args.hidden_size,
        "num_layers": args.num_layers,
        "dropout": args.dropout,
        "batch_size": args.batch_size,
        "epochs": args.epochs,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "patience": args.patience,
        "seed": args.seed,
        "symbol_count": int(prepared_df["symbol"].nunique()),
        "feature_columns": feature_columns,
        "target_column": target_column,
        "target_return_column": target_return_column,
        "split_summary": split_summary,
        "expert_name": PROFILE_NAME,
        "config": config,
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

    normalizer = FeatureNormalizer.fit(train_df, feature_columns)
    normalized_full = normalizer.transform(prepared_df)

    try:
        X_all, y_all, meta_all = build_sequence_samples(
            normalized_full,
            feature_columns,
            args.seq_len,
            target_column,
            target_return_column=target_return_column,
        )
    except Exception as exc:
        print(f"[ERROR] Failed to build sequence samples: {exc}")
        return 1

    if len(X_all) == 0:
        print("[ERROR] No sequence samples remain after feature preparation.")
        return 1

    train_dates = set(split_summary["train_dates"])
    valid_dates = set(split_summary["valid_dates"])
    test_dates = set(split_summary["test_dates"])
    meta_dates = meta_all["date"].dt.strftime("%Y-%m-%d")
    train_mask = meta_dates.isin(train_dates).to_numpy()
    valid_mask = meta_dates.isin(valid_dates).to_numpy()
    test_mask = meta_dates.isin(test_dates).to_numpy()

    X_train, y_train, train_meta = X_all[train_mask], y_all[train_mask], meta_all[train_mask].copy()
    X_valid, y_valid, valid_meta = X_all[valid_mask], y_all[valid_mask], meta_all[valid_mask].copy()
    X_test, y_test, test_meta = X_all[test_mask], y_all[test_mask], meta_all[test_mask].copy()

    if len(X_train) == 0 or len(X_valid) == 0 or len(X_test) == 0:
        print("[ERROR] Time split produced an empty train, valid, or test sequence split.")
        return 1

    device = resolve_device(args.device)
    input_size = int(X_train.shape[-1])
    model = build_lstm_model(
        input_size=input_size,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
        mode=args.mode,
    ).to(device)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=args.weight_decay,
    )
    if args.mode == "classification":
        positives = float((y_train >= 0.5).sum())
        negatives = float((y_train < 0.5).sum())
        pos_weight = torch.tensor(
            [negatives / max(positives, 1.0)],
            dtype=torch.float32,
            device=device,
        )
        criterion: nn.Module = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    else:
        criterion = nn.SmoothL1Loss(beta=0.01)

    train_loader = build_loader(X_train, y_train, args.batch_size, shuffle=True)
    valid_loader = build_loader(X_valid, y_valid, args.batch_size, shuffle=False)
    history: list[dict[str, float]] = []
    best_state = copy.deepcopy(model.state_dict())
    best_valid_loss = float("inf")
    best_epoch = 0
    patience_left = args.patience

    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss_total = 0.0
        train_count = 0
        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch_x).squeeze(-1)
            if args.mode == "classification":
                loss = criterion(logits, batch_y)
            else:
                loss = criterion(logits, batch_y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            batch_size = int(len(batch_x))
            train_loss_total += float(loss.item()) * batch_size
            train_count += batch_size

        model.eval()
        valid_loss_total = 0.0
        valid_count = 0
        with torch.no_grad():
            for batch_x, batch_y in valid_loader:
                batch_x = batch_x.to(device)
                batch_y = batch_y.to(device)
                logits = model(batch_x).squeeze(-1)
                loss = criterion(logits, batch_y)
                batch_size = int(len(batch_x))
                valid_loss_total += float(loss.item()) * batch_size
                valid_count += batch_size

        train_loss = train_loss_total / max(train_count, 1)
        valid_loss = valid_loss_total / max(valid_count, 1)
        history.append({"epoch": epoch, "train_loss": train_loss, "valid_loss": valid_loss})
        print(f"[INFO] epoch={epoch:03d} train_loss={train_loss:.6f} valid_loss={valid_loss:.6f}")

        if valid_loss < best_valid_loss - 1e-6:
            best_valid_loss = valid_loss
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            patience_left = args.patience
        else:
            patience_left -= 1
            if patience_left <= 0:
                print(f"[INFO] Early stopping triggered at epoch {epoch}.")
                break

    model.load_state_dict(best_state)

    train_metrics, train_scores = evaluate_split(
        model,
        X_train,
        y_train,
        mode=args.mode,
        batch_size=args.batch_size,
        device=device,
    )
    valid_metrics, valid_scores = evaluate_split(
        model,
        X_valid,
        y_valid,
        mode=args.mode,
        batch_size=args.batch_size,
        device=device,
    )
    test_metrics, test_scores = evaluate_split(
        model,
        X_test,
        y_test,
        mode=args.mode,
        batch_size=args.batch_size,
        device=device,
    )

    predictions = test_meta.copy()
    if args.mode == "classification":
        predictions["pred_probability"] = test_scores
        predictions["pred_label"] = (predictions["pred_probability"] >= 0.5).astype(int)
    else:
        predictions["pred_return"] = test_scores

    predictions["date"] = pd.to_datetime(predictions["date"]).dt.strftime("%Y-%m-%d")
    predictions_to_save = predictions.copy()
    predictions_to_save.to_csv(output_dir / "test_predictions.csv", index=False, encoding="utf-8")

    checkpoint_path = output_dir / "model.pt"
    checkpoint_payload = build_checkpoint_payload(
        model=model,
        config=config,
        normalizer=normalizer,
        feature_columns=feature_columns,
        target_column=target_column,
        target_return_column=target_return_column,
        mode=args.mode,
    )
    save_checkpoint(checkpoint_path, checkpoint_payload)

    metrics = {
        "input_csv": str(input_path),
        "prepared_csv": str(prepared_path),
        "model_path": str(checkpoint_path),
        "mode": args.mode,
        "horizon": args.horizon,
        "threshold": args.threshold,
        "seq_len": args.seq_len,
        "hidden_size": args.hidden_size,
        "num_layers": args.num_layers,
        "dropout": args.dropout,
        "batch_size": args.batch_size,
        "epochs": args.epochs,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "patience": args.patience,
        "seed": args.seed,
        "feature_columns": feature_columns,
        "target_column": target_column,
        "target_return_column": target_return_column,
        "split_summary": split_summary,
        "history": history,
        "best_epoch": best_epoch,
        "best_valid_loss": best_valid_loss,
        "train_metrics": train_metrics,
        "valid_metrics": valid_metrics,
        "test_metrics": test_metrics,
        "train_rows": int(len(train_meta)),
        "valid_rows": int(len(valid_meta)),
        "test_rows": int(len(test_meta)),
        "train_symbols": int(train_meta["symbol"].nunique()),
        "valid_symbols": int(valid_meta["symbol"].nunique()),
        "test_symbols": int(test_meta["symbol"].nunique()),
        "config": config,
        "normalizer": normalizer.to_dict(),
        "expert_name": PROFILE_NAME,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Prepared dataset: {prepared_path}")
    print(f"[OK] Metrics file: {output_dir / 'metrics.json'}")
    print(f"[OK] Predictions file: {output_dir / 'test_predictions.csv'}")
    print(f"[OK] Model file: {checkpoint_path}")
    print(f"[INFO] Test rows: {len(test_meta)}")
    print(f"[INFO] Test metrics: {json.dumps(test_metrics, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
