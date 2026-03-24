#!/usr/bin/env python3
"""Train a real XGBoost stock expert on the shared normalized schema."""

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
    choose_feature_columns,
    output_dir_for,
    prepare_base_frame,
)
from model_prediction.lightgbm.scripts.train_lightgbm import (
    classification_metrics,
    ranking_metrics,
    regression_metrics,
    split_by_date,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train an XGBoost stock model or prepare an aligned dataset."
    )
    parser.add_argument("input_csv", help="Normalized CSV path produced by the fetcher.")
    parser.add_argument("--output-dir", default="", help="Directory used to store artifacts.")
    parser.add_argument(
        "--mode",
        default="classification",
        choices=["classification", "regression", "ranking"],
        help="Choose binary direction prediction, future-return regression, or ranking.",
    )
    parser.add_argument("--horizon", type=int, default=5, help="Forecast horizon in trading days.")
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
        "--num-boost-round",
        type=int,
        default=300,
        help="Maximum number of boosting rounds.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Prepare features and targets without fitting the model.",
    )
    return parser.parse_args()


def _base_prediction_columns(
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


def _save_feature_importance(booster, feature_columns: list[str], output_dir: Path) -> Path:
    gain_map = booster.get_score(importance_type="gain")
    weight_map = booster.get_score(importance_type="weight")
    importance_df = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance_gain": [float(gain_map.get(column, 0.0)) for column in feature_columns],
            "importance_weight": [float(weight_map.get(column, 0.0)) for column in feature_columns],
        }
    ).sort_values("importance_gain", ascending=False, kind="stable")
    path = output_dir / "feature_importance.csv"
    importance_df.to_csv(path, index=False, encoding="utf-8")
    return path


def _build_dmatrix(xgb_module, df: pd.DataFrame, feature_columns: list[str], label_column: str):
    matrix = xgb_module.DMatrix(
        df[feature_columns],
        label=df[label_column].to_numpy(),
        feature_names=feature_columns,
    )
    return matrix


def _apply_group_sizes(dmatrix, df: pd.DataFrame) -> None:
    group_sizes = (
        df.groupby(df["date"].dt.strftime("%Y-%m-%d"), sort=True).size().astype(int).tolist()
    )
    dmatrix.set_group(group_sizes)


def train_xgboost(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    test_df: pd.DataFrame,
    *,
    feature_columns: list[str],
    target_column: str,
    target_return_column: str,
    mode: str,
    num_boost_round: int,
    output_dir: Path,
) -> tuple[dict[str, object], pd.DataFrame, Path, Path]:
    try:
        import xgboost as xgb
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "xgboost is not installed. Install project dependencies or rerun with --prepare-only."
        ) from exc

    train_matrix = _build_dmatrix(xgb, train_df, feature_columns, target_column)
    valid_matrix = _build_dmatrix(xgb, valid_df, feature_columns, target_column)
    test_matrix = _build_dmatrix(xgb, test_df, feature_columns, target_column)

    params: dict[str, object] = {
        "eta": 0.05,
        "max_depth": 6,
        "min_child_weight": 20.0,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "lambda": 1.0,
        "alpha": 0.0,
        "seed": 42,
        "tree_method": "hist",
        "verbosity": 0,
    }
    if mode == "classification":
        params.update({"objective": "binary:logistic", "eval_metric": ["logloss", "auc"]})
    elif mode == "ranking":
        params.update(
            {
                "objective": "rank:ndcg",
                "eval_metric": ["ndcg@5", "ndcg@10"],
            }
        )
        _apply_group_sizes(train_matrix, train_df)
        _apply_group_sizes(valid_matrix, valid_df)
        _apply_group_sizes(test_matrix, test_df)
    else:
        params.update({"objective": "reg:squarederror", "eval_metric": ["mae", "rmse"]})

    evals = [(train_matrix, "train"), (valid_matrix, "valid")]
    booster = xgb.train(
        params=params,
        dtrain=train_matrix,
        num_boost_round=num_boost_round,
        evals=evals,
        early_stopping_rounds=50,
        verbose_eval=False,
    )

    best_iteration = int(getattr(booster, "best_iteration", -1))
    iteration_range = None
    if best_iteration >= 0:
        iteration_range = (0, best_iteration + 1)
    test_scores = booster.predict(test_matrix, iteration_range=iteration_range)

    prediction_columns = _base_prediction_columns(test_df, target_return_column, target_column)
    predictions = test_df[prediction_columns].copy()
    if mode == "classification":
        predictions["pred_probability"] = test_scores
        predictions["pred_label"] = (predictions["pred_probability"] >= 0.5).astype(int)
        metrics = classification_metrics(
            test_df[target_column].to_numpy().astype(int),
            predictions["pred_probability"].to_numpy(),
        )
    elif mode == "ranking":
        predictions["pred_score"] = test_scores
        predictions["pred_rank"] = predictions.groupby("date")["pred_score"].rank(
            ascending=False, method="first"
        )
        metrics = ranking_metrics(
            test_df[target_column].to_numpy(),
            predictions["pred_score"].to_numpy(),
            test_df[target_return_column].to_numpy(),
        )
    else:
        predictions["pred_return"] = test_scores
        metrics = regression_metrics(
            test_df[target_column].to_numpy(),
            predictions["pred_return"].to_numpy(),
        )

    model_path = output_dir / "model.json"
    booster.save_model(model_path)
    importance_path = _save_feature_importance(booster, feature_columns, output_dir)
    metrics["best_iteration"] = best_iteration + 1 if best_iteration >= 0 else num_boost_round
    metrics["model_path"] = str(model_path)
    return metrics, predictions, model_path, importance_path


def main() -> int:
    args = parse_args()
    output_dir = output_dir_for(PROJECT_ROOT, "xgboost", args)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input_csv)
    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        return 1

    try:
        feature_df, target_column, target_return_column = prepare_base_frame(
            input_path,
            mode=args.mode,
            horizon=args.horizon,
            threshold=args.threshold,
        )
        feature_df, extra_columns = add_xgboost_style_features(feature_df)
        feature_columns = choose_feature_columns(feature_df, extra_columns=extra_columns)
        if not feature_columns:
            raise ValueError("No feature columns were generated.")
        prepared_df = feature_df.dropna(subset=feature_columns + [target_column]).copy()
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

    summary = {
        "input_csv": str(input_path),
        "prepared_csv": str(prepared_path),
        "mode": args.mode,
        "horizon": args.horizon,
        "threshold": args.threshold,
        "symbol_count": int(prepared_df["symbol"].nunique()),
        "feature_columns": feature_columns,
        "target_column": target_column,
        "target_return_column": target_return_column,
        "split_summary": split_summary,
        "expert_name": "xgboost",
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
        metrics, predictions, model_path, importance_path = train_xgboost(
            train_df,
            valid_df,
            test_df,
            feature_columns=feature_columns,
            target_column=target_column,
            target_return_column=target_return_column,
            mode=args.mode,
            num_boost_round=args.num_boost_round,
            output_dir=output_dir,
        )
    except Exception as exc:
        print(f"[ERROR] Training failed: {exc}")
        return 1

    predictions_to_save = predictions.copy()
    predictions_to_save["date"] = pd.to_datetime(predictions_to_save["date"]).dt.strftime("%Y-%m-%d")
    predictions_path = output_dir / "test_predictions.csv"
    predictions_to_save.to_csv(predictions_path, index=False, encoding="utf-8")

    metrics_payload = summary | {
        "metrics": metrics,
        "model_path": str(model_path),
        "feature_importance_path": str(importance_path),
    }
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Prepared dataset: {prepared_path}")
    print(f"[OK] Metrics file: {metrics_path}")
    print(f"[OK] Predictions file: {predictions_path}")
    print(f"[OK] Model file: {model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
