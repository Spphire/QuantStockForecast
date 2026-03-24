#!/usr/bin/env python3
"""Train a LightGBM stock baseline on the shared normalized schema."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from data_module.common.stock_schema import normalize_dataframe


DEFAULT_FEATURES = [
    "intraday_return",
    "range_pct",
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "close_ma5_gap",
    "close_ma10_gap",
    "close_ma20_gap",
    "close_ma60_gap",
    "volume_ma5_ratio",
    "volume_ma20_ratio",
    "volatility_5d",
    "volatility_10d",
    "volatility_20d",
    "breakout_20d",
    "distance_to_low_20d",
    "price_position_20d",
    "volume_zscore_20d",
    "market_return_1d",
    "market_return_5d",
    "relative_return_1d",
    "relative_return_5d",
    "cs_rank_return_1d",
    "cs_rank_return_5d",
    "cs_rank_return_20d",
    "cs_rank_volume_ma5_ratio",
    "cs_rank_turnover",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a LightGBM stock model or prepare an aligned modeling dataset."
    )
    parser.add_argument("input_csv", help="Normalized CSV path produced by the fetcher.")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory used to store prepared data, metrics, and model artifacts.",
    )
    parser.add_argument(
        "--mode",
        default="classification",
        choices=["classification", "regression", "ranking"],
        help="Choose binary direction prediction or future-return regression.",
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
        "--num-boost-round",
        type=int,
        default=300,
        help="Boosting rounds used when training LightGBM.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Prepare features and targets without fitting a LightGBM model.",
    )
    return parser.parse_args()


def output_dir_for(args: argparse.Namespace) -> Path:
    if args.output_dir:
        return Path(args.output_dir)

    input_stem = Path(args.input_csv).stem
    run_name = f"{input_stem}_{args.mode}_{args.horizon}d"
    return PROJECT_ROOT / "model_prediction" / "lightgbm" / "artifacts" / run_name


def ensure_symbol_column(df: pd.DataFrame) -> pd.DataFrame:
    working = df.copy()
    if "symbol" not in working.columns or working["symbol"].replace("", np.nan).isna().all():
        working["symbol"] = "UNKNOWN"
    return working


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    working = ensure_symbol_column(df)
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"]).sort_values(["symbol", "date"], kind="stable").copy()

    grouped = working.groupby("symbol", group_keys=False)

    working["intraday_return"] = working["close"] / working["open"] - 1.0
    working["range_pct"] = working["high"] / working["low"] - 1.0
    working["return_1d"] = grouped["close"].pct_change(1)
    working["return_5d"] = grouped["close"].pct_change(5)
    working["return_10d"] = grouped["close"].pct_change(10)
    working["return_20d"] = grouped["close"].pct_change(20)

    for window in [5, 10, 20, 60]:
        close_ma = grouped["close"].transform(lambda series: series.rolling(window).mean())
        working[f"close_ma{window}_gap"] = working["close"] / close_ma - 1.0

    for window in [5, 20]:
        volume_ma = grouped["volume"].transform(lambda series: series.rolling(window).mean())
        working[f"volume_ma{window}_ratio"] = working["volume"] / volume_ma

    for window in [5, 10, 20]:
        working[f"volatility_{window}d"] = grouped["return_1d"].transform(
            lambda series: series.rolling(window).std()
        )

    high_20 = grouped["high"].transform(lambda series: series.rolling(20).max())
    low_20 = grouped["low"].transform(lambda series: series.rolling(20).min())
    working["breakout_20d"] = working["close"] / high_20 - 1.0
    working["distance_to_low_20d"] = working["close"] / low_20 - 1.0
    price_range_20 = (high_20 - low_20).replace(0, np.nan)
    working["price_position_20d"] = (working["close"] - low_20) / price_range_20

    volume_mean_20 = grouped["volume"].transform(lambda series: series.rolling(20).mean())
    volume_std_20 = grouped["volume"].transform(lambda series: series.rolling(20).std())
    working["volume_zscore_20d"] = (working["volume"] - volume_mean_20) / volume_std_20

    if "amount" in working.columns:
        amount_ma = grouped["amount"].transform(lambda series: series.rolling(5).mean())
        working["amount_ma5_ratio"] = working["amount"] / amount_ma

    for column in ["turnover", "pct_change", "amplitude", "price_change"]:
        if column in working.columns:
            working[column] = pd.to_numeric(working[column], errors="coerce")

    if len(working["symbol"].replace("", np.nan).dropna().unique()) > 1:
        market_return_1d = working.groupby("date")["return_1d"].transform("mean")
        market_return_5d = working.groupby("date")["return_5d"].transform("mean")
        working["market_return_1d"] = market_return_1d
        working["market_return_5d"] = market_return_5d
        working["relative_return_1d"] = working["return_1d"] - market_return_1d
        working["relative_return_5d"] = working["return_5d"] - market_return_5d
        working["cs_rank_return_1d"] = working.groupby("date")["return_1d"].rank(pct=True)
        working["cs_rank_return_5d"] = working.groupby("date")["return_5d"].rank(pct=True)
        working["cs_rank_return_20d"] = working.groupby("date")["return_20d"].rank(pct=True)
        working["cs_rank_volume_ma5_ratio"] = working.groupby("date")["volume_ma5_ratio"].rank(
            pct=True
        )
        if "turnover" in working.columns:
            working["cs_rank_turnover"] = working.groupby("date")["turnover"].rank(pct=True)

    return working


def add_targets(
    df: pd.DataFrame, mode: str, horizon: int, threshold: float
) -> tuple[pd.DataFrame, str, str]:
    working = df.copy()
    grouped = working.groupby("symbol", group_keys=False)
    target_return_column = f"target_return_{horizon}d"
    working[target_return_column] = grouped["close"].shift(-horizon) / working["close"] - 1.0

    if mode == "classification":
        target_column = f"target_up_{horizon}d"
        labels = (working[target_return_column] > threshold).astype(float)
        working[target_column] = labels.where(working[target_return_column].notna(), np.nan)
    elif mode == "ranking":
        target_column = f"target_rank_{horizon}d"
        rank_pct = working.groupby("date")[target_return_column].rank(pct=True, method="average")
        working[target_column] = ((rank_pct * 10).clip(upper=9.9999)).fillna(0).astype(int)
    else:
        target_column = target_return_column

    return working, target_column, target_return_column


def select_feature_columns(df: pd.DataFrame) -> list[str]:
    features = [column for column in DEFAULT_FEATURES if column in df.columns]
    for optional in ["amount_ma5_ratio", "turnover", "pct_change", "amplitude", "price_change"]:
        if optional in df.columns:
            features.append(optional)
    return features


def split_by_date(
    df: pd.DataFrame,
    train_ratio: float,
    valid_ratio: float,
    *,
    label_horizon: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    unique_dates = sorted(df["date"].dt.strftime("%Y-%m-%d").unique())
    if len(unique_dates) < 20:
        raise ValueError("Need at least 20 unique dates after feature engineering to create stable time splits.")

    horizon = max(int(label_horizon), 0)
    train_cut = max(1, int(len(unique_dates) * train_ratio))
    valid_cut = max(train_cut + 1, int(len(unique_dates) * (train_ratio + valid_ratio)))
    valid_cut = min(valid_cut, len(unique_dates) - 1)

    train_date_list = list(unique_dates[:train_cut])
    valid_date_list = list(unique_dates[train_cut:valid_cut])
    test_date_list = list(unique_dates[valid_cut:])

    purged_train_dates = 0
    purged_valid_dates = 0
    if horizon > 0:
        if len(train_date_list) <= horizon:
            raise ValueError(
                "Train split is too short for the requested horizon purge. "
                "Increase train range or reduce --horizon."
            )
        if len(valid_date_list) <= horizon:
            raise ValueError(
                "Validation split is too short for the requested horizon purge. "
                "Increase valid range or reduce --horizon."
            )
        train_date_list = train_date_list[:-horizon]
        valid_date_list = valid_date_list[:-horizon]
        purged_train_dates = horizon
        purged_valid_dates = horizon

    train_dates = set(train_date_list)
    valid_dates = set(valid_date_list)
    test_dates = set(test_date_list)

    if not train_dates or not valid_dates or not test_dates:
        raise ValueError("Time split failed. Adjust ratios or use a longer date range.")

    date_str = df["date"].dt.strftime("%Y-%m-%d")
    train_df = df[date_str.isin(train_dates)].copy()
    valid_df = df[date_str.isin(valid_dates)].copy()
    test_df = df[date_str.isin(test_dates)].copy()

    summary = {
        "train_rows": int(len(train_df)),
        "valid_rows": int(len(valid_df)),
        "test_rows": int(len(test_df)),
        "train_symbols": int(train_df["symbol"].nunique()),
        "valid_symbols": int(valid_df["symbol"].nunique()),
        "test_symbols": int(test_df["symbol"].nunique()),
        "train_date_min": min(train_dates),
        "train_date_max": max(train_dates),
        "valid_date_min": min(valid_dates),
        "valid_date_max": max(valid_dates),
        "test_date_min": min(test_dates),
        "test_date_max": max(test_dates),
        "label_horizon": horizon,
        "purged_train_dates": purged_train_dates,
        "purged_valid_dates": purged_valid_dates,
    }
    return train_df, valid_df, test_df, summary


def auc_score(y_true: np.ndarray, y_score: np.ndarray) -> float | None:
    positives = int((y_true == 1).sum())
    negatives = int((y_true == 0).sum())
    if positives == 0 or negatives == 0:
        return None
    ranks = pd.Series(y_score).rank(method="average").to_numpy()
    rank_sum = ranks[y_true == 1].sum()
    return float((rank_sum - positives * (positives + 1) / 2) / (positives * negatives))


def classification_metrics(
    y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5
) -> dict[str, float | None]:
    y_pred = (y_prob >= threshold).astype(int)
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    clipped = np.clip(y_prob, 1e-12, 1 - 1e-12)
    logloss = float(-(y_true * np.log(clipped) + (1 - y_true) * np.log(1 - clipped)).mean())

    return {
        "accuracy": float((y_pred == y_true).mean()),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "logloss": logloss,
        "auc": auc_score(y_true, y_prob),
        "positive_rate": float(y_true.mean()),
        "predicted_positive_rate": float(y_pred.mean()),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | None]:
    errors = y_pred - y_true
    correlation = None
    if len(y_true) > 1 and np.std(y_true) > 0 and np.std(y_pred) > 0:
        correlation = float(np.corrcoef(y_true, y_pred)[0, 1])

    return {
        "mae": float(np.abs(errors).mean()),
        "rmse": float(math.sqrt(np.square(errors).mean())),
        "directional_accuracy": float(((y_true >= 0) == (y_pred >= 0)).mean()),
        "mean_actual": float(y_true.mean()),
        "mean_predicted": float(y_pred.mean()),
        "correlation": correlation,
    }


def ranking_metrics(y_true_rank: np.ndarray, y_score: np.ndarray, y_return: np.ndarray) -> dict[str, float | None]:
    y_true_rank = np.asarray(y_true_rank, dtype=float).reshape(-1)
    y_score = np.asarray(y_score, dtype=float).reshape(-1)
    y_return = np.asarray(y_return, dtype=float).reshape(-1)

    valid_mask = np.isfinite(y_score) & np.isfinite(y_return)
    if not valid_mask.any():
        return {
            "rank_label_mean": float(np.mean(y_true_rank)) if len(y_true_rank) else 0.0,
            "score_mean": float(np.mean(y_score)) if len(y_score) else 0.0,
            "return_correlation": None,
            "top_decile_mean_return": None,
            "bottom_decile_mean_return": None,
            "top_bottom_spread": None,
        }

    y_score = y_score[valid_mask]
    y_return = y_return[valid_mask]

    correlation = None
    if len(y_return) > 1 and np.std(y_score) > 0 and np.std(y_return) > 0:
        correlation = float(np.corrcoef(y_score, y_return)[0, 1])

    top_decile = max(1, int(len(y_score) * 0.1))
    order = np.argsort(-y_score)
    top_returns = y_return[order][:top_decile]
    bottom_returns = y_return[order][-top_decile:]

    return {
        "rank_label_mean": float(np.mean(y_true_rank)),
        "score_mean": float(np.mean(y_score)),
        "return_correlation": correlation,
        "top_decile_mean_return": float(np.mean(top_returns)),
        "bottom_decile_mean_return": float(np.mean(bottom_returns)),
        "top_bottom_spread": float(np.mean(top_returns) - np.mean(bottom_returns)),
    }


def group_sizes_by_date(df: pd.DataFrame) -> list[int]:
    return (
        df.groupby(df["date"].dt.strftime("%Y-%m-%d"), sort=True)
        .size()
        .astype(int)
        .tolist()
    )


def train_lightgbm(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    target_return_column: str,
    mode: str,
    num_boost_round: int,
    output_dir: Path,
) -> tuple[dict[str, object], pd.DataFrame]:
    try:
        import lightgbm as lgb
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "lightgbm is not installed. Install project dependencies or rerun with --prepare-only."
        ) from exc

    dataset_kwargs = {"feature_name": feature_columns}
    if mode == "ranking":
        dataset_kwargs["group"] = group_sizes_by_date(train_df)

    train_dataset = lgb.Dataset(
        train_df[feature_columns].to_numpy(),
        label=train_df[target_column].to_numpy(),
        **dataset_kwargs,
    )

    valid_kwargs = {"reference": train_dataset, "feature_name": feature_columns}
    if mode == "ranking":
        valid_kwargs["group"] = group_sizes_by_date(valid_df)

    valid_dataset = lgb.Dataset(
        valid_df[feature_columns].to_numpy(),
        label=valid_df[target_column].to_numpy(),
        **valid_kwargs,
    )

    params = {
        "learning_rate": 0.05,
        "num_leaves": 31,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "min_data_in_leaf": 25,
        "seed": 42,
        "verbosity": -1,
    }
    if mode == "classification":
        params.update({"objective": "binary", "metric": ["binary_logloss", "auc"]})
    elif mode == "ranking":
        params.update(
            {
                "objective": "lambdarank",
                "metric": ["ndcg"],
                "ndcg_eval_at": [5, 10],
                "label_gain": list(range(0, 101)),
            }
        )
    else:
        params.update({"objective": "regression", "metric": ["l1", "l2"]})

    callbacks = []
    if hasattr(lgb, "early_stopping"):
        callbacks.append(lgb.early_stopping(stopping_rounds=50, verbose=False))
    if hasattr(lgb, "log_evaluation"):
        callbacks.append(lgb.log_evaluation(period=50))

    booster = lgb.train(
        params=params,
        train_set=train_dataset,
        num_boost_round=num_boost_round,
        valid_sets=[valid_dataset],
        valid_names=["valid"],
        callbacks=callbacks,
    )

    model_path = output_dir / "model.txt"
    model_text = booster.model_to_string(
        num_iteration=int(getattr(booster, "best_iteration", 0) or num_boost_round)
    )
    model_path.write_text(model_text, encoding="utf-8")

    test_scores = booster.predict(test_df[feature_columns].to_numpy())
    base_prediction_columns = ["date", "symbol", "close"]
    for optional_column in ["amount", "turnover", "volume"]:
        if optional_column in test_df.columns:
            base_prediction_columns.append(optional_column)
    base_prediction_columns.append(target_return_column)
    if target_column != target_return_column:
        base_prediction_columns.append(target_column)
    predictions = test_df[base_prediction_columns].copy()

    if mode == "classification":
        predictions["pred_probability"] = test_scores
        predictions["pred_label"] = (test_scores >= 0.5).astype(int)
        metrics = classification_metrics(
            test_df[target_column].to_numpy().astype(int),
            predictions["pred_probability"].to_numpy(),
        )
    elif mode == "ranking":
        predictions["pred_score"] = test_scores
        predictions["pred_rank"] = (
            predictions.groupby("date")["pred_score"].rank(ascending=False, method="first")
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

    importance_df = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance_split": booster.feature_importance(importance_type="split"),
            "importance_gain": booster.feature_importance(importance_type="gain"),
        }
    ).sort_values("importance_gain", ascending=False, kind="stable")
    importance_df.to_csv(output_dir / "feature_importance.csv", index=False, encoding="utf-8")

    metrics["best_iteration"] = int(getattr(booster, "best_iteration", 0) or num_boost_round)
    metrics["model_path"] = str(model_path)
    return metrics, predictions


def main() -> int:
    args = parse_args()
    output_dir = output_dir_for(args)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input_csv)
    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        return 1

    try:
        raw_df = pd.read_csv(input_path, encoding="utf-8-sig")
        normalized_df = normalize_dataframe(raw_df)
        feature_df = engineer_features(normalized_df)
        feature_df, target_column, target_return_column = add_targets(
            feature_df, args.mode, args.horizon, args.threshold
        )
        feature_columns = select_feature_columns(feature_df)
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
    prepared_to_save["date"] = prepared_to_save["date"].dt.strftime("%Y-%m-%d")
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
        metrics, predictions = train_lightgbm(
            train_df,
            valid_df,
            test_df,
            feature_columns,
            target_column,
            target_return_column,
            args.mode,
            args.num_boost_round,
            output_dir,
        )
    except Exception as exc:
        print(f"[ERROR] Training failed: {exc}")
        return 1

    predictions_to_save = predictions.copy()
    predictions_to_save["date"] = predictions_to_save["date"].dt.strftime("%Y-%m-%d")
    predictions_to_save.to_csv(
        output_dir / "test_predictions.csv", index=False, encoding="utf-8"
    )

    full_summary = summary | {"metrics": metrics}
    (output_dir / "metrics.json").write_text(
        json.dumps(full_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Prepared dataset: {prepared_path}")
    print(f"[OK] Metrics file: {output_dir / 'metrics.json'}")
    print(f"[OK] Predictions file: {output_dir / 'test_predictions.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
