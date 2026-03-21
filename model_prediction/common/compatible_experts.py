"""Shared numpy-based expert pipelines for model_prediction modules.

These helpers keep the xgboost, catboost, lstm, and transformer modules
aligned on the same dataset contract and artifact layout, while allowing each
module to define a slightly different feature view.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from data_module.common.stock_schema import normalize_dataframe
from model_prediction.lightgbm.scripts.train_lightgbm import (
    add_targets,
    classification_metrics,
    engineer_features,
    ranking_metrics,
    regression_metrics,
    select_feature_columns,
    split_by_date,
)


def output_dir_for(project_root: Path, module_name: str, args: Any) -> Path:
    if getattr(args, "output_dir", ""):
        return Path(args.output_dir)
    input_stem = Path(args.input_csv).stem
    run_name = f"{input_stem}_{args.mode}_{args.horizon}d"
    return project_root / "model_prediction" / module_name / "artifacts" / run_name


def normalize_optional_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    working = df.copy()
    for column in columns:
        if column in working.columns:
            working[column] = pd.to_numeric(working[column], errors="coerce")
    return working


def neutral_fill_value(column: str) -> float:
    if column.startswith("cs_rank_") or "price_position" in column:
        return 0.5
    return 0.0


def add_calendar_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    working = df.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working["weekday"] = working["date"].dt.weekday.astype(float)
    working["month"] = working["date"].dt.month.astype(float)
    weekday_angle = 2.0 * math.pi * working["weekday"] / 7.0
    month_angle = 2.0 * math.pi * (working["month"] - 1.0) / 12.0
    working["weekday_sin"] = np.sin(weekday_angle)
    working["weekday_cos"] = np.cos(weekday_angle)
    working["month_sin"] = np.sin(month_angle)
    working["month_cos"] = np.cos(month_angle)
    return working, ["weekday", "month", "weekday_sin", "weekday_cos", "month_sin", "month_cos"]


def add_xgboost_style_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    working = df.copy()
    feature_pairs = [
        ("return_1d", "volatility_20d", "return_1d_x_volatility_20d"),
        ("return_5d", "close_ma20_gap", "return_5d_x_close_ma20_gap"),
        ("market_return_5d", "relative_return_1d", "market_x_relative_1d"),
        ("cs_rank_return_1d", "cs_rank_turnover", "rank1_x_turnover"),
        ("volume_ma5_ratio", "volume_zscore_20d", "volume_ratio_x_zscore"),
        ("price_position_20d", "distance_to_low_20d", "position_x_distance"),
    ]
    added: list[str] = []
    for left, right, name in feature_pairs:
        if left in working.columns and right in working.columns:
            working[name] = pd.to_numeric(working[left], errors="coerce") * pd.to_numeric(
                working[right], errors="coerce"
            )
            added.append(name)
    for column in ["return_1d", "return_5d", "volatility_20d", "close_ma20_gap", "volume_ma5_ratio"]:
        if column in working.columns:
            square_name = f"{column}_sq"
            working[square_name] = pd.to_numeric(working[column], errors="coerce") ** 2
            added.append(square_name)
    return working, added


def add_sequence_features(
    df: pd.DataFrame,
    *,
    base_columns: list[str],
    window: int,
    summary_mode: str = "mean_std_trend",
) -> tuple[pd.DataFrame, list[str]]:
    working = df.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"]).sort_values(["symbol", "date"], kind="stable").copy()
    grouped = working.groupby("symbol", group_keys=False)

    added: list[str] = []
    for column in base_columns:
        if column not in working.columns:
            continue
        series = pd.to_numeric(working[column], errors="coerce")
        working[column] = series
        lag_cols: list[str] = []
        for lag in range(1, window + 1):
            lag_name = f"{column}_lag{lag}"
            working[lag_name] = grouped[column].shift(lag)
            lag_cols.append(lag_name)
            added.append(lag_name)

        lag_frame = working[lag_cols]
        mean_name = f"{column}_lag_mean_{window}"
        std_name = f"{column}_lag_std_{window}"
        min_name = f"{column}_lag_min_{window}"
        max_name = f"{column}_lag_max_{window}"
        trend_name = f"{column}_lag_trend_{window}"
        last_name = f"{column}_lag_last_{window}"
        weighted_name = f"{column}_lag_weighted_mean_{window}"
        working[mean_name] = lag_frame.mean(axis=1)
        working[std_name] = lag_frame.std(axis=1)
        working[min_name] = lag_frame.min(axis=1)
        working[max_name] = lag_frame.max(axis=1)
        working[trend_name] = working[f"{column}_lag1"] - working[f"{column}_lag{window}"]
        working[last_name] = working[f"{column}_lag1"]
        added.extend([mean_name, std_name, min_name, max_name, trend_name, last_name])
        if "weighted" in summary_mode:
            weights = np.linspace(1.0, 2.0, window, dtype=float)
            weights = weights / weights.sum()
            working[weighted_name] = lag_frame.to_numpy(dtype=float) @ weights
            added.append(weighted_name)

    return working, added


def compute_symbol_target_encoding(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    test_df: pd.DataFrame,
    *,
    symbol_column: str,
    target_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    global_mean = float(pd.to_numeric(train_df[target_column], errors="coerce").mean())
    encoding = (
        train_df.groupby(symbol_column)[target_column]
        .agg(["mean", "size"])
        .rename(columns={"mean": "symbol_target_mean", "size": "symbol_count"})
        .reset_index()
    )
    encoding[symbol_column] = encoding[symbol_column].astype(str)

    def _apply(frame: pd.DataFrame) -> pd.DataFrame:
        working = frame.copy()
        working[symbol_column] = working[symbol_column].astype(str)
        merged = working.merge(encoding, on=symbol_column, how="left")
        merged["symbol_target_mean"] = merged["symbol_target_mean"].fillna(global_mean)
        merged["symbol_count"] = merged["symbol_count"].fillna(0.0)
        return merged

    return _apply(train_df), _apply(valid_df), _apply(test_df), {
        "global_mean": global_mean,
        "encoding": encoding.to_dict(orient="records"),
        "symbol_column": symbol_column,
        "target_column": target_column,
    }


def apply_symbol_encoding_from_state(
    df: pd.DataFrame,
    state: dict[str, Any],
) -> pd.DataFrame:
    encoding_state = state.get("symbol_encoding", {})
    encoding_rows = list(encoding_state.get("encoding", []))
    symbol_column = str(encoding_state.get("symbol_column", "symbol"))
    global_mean = float(encoding_state.get("global_mean", 0.0))

    if not encoding_rows:
        working = df.copy()
        working["symbol_target_mean"] = global_mean
        working["symbol_count"] = 0.0
        return working

    encoding = pd.DataFrame(encoding_rows)
    encoding[symbol_column] = encoding[symbol_column].astype(str)
    working = df.copy()
    working[symbol_column] = working[symbol_column].astype(str)
    merged = working.merge(encoding, on=symbol_column, how="left")
    merged["symbol_target_mean"] = merged["symbol_target_mean"].fillna(global_mean)
    merged["symbol_count"] = merged["symbol_count"].fillna(0.0)
    return merged


def _sigmoid(x: np.ndarray) -> np.ndarray:
    clipped = np.clip(x, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def fit_linear_model(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    test_df: pd.DataFrame,
    *,
    feature_columns: list[str],
    target_column: str,
    target_return_column: str,
    mode: str,
    num_steps: int,
    learning_rate: float,
    reg_strength: float,
    profile_name: str,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]:
    X_train, feature_means, feature_stds = _prepare_matrix(train_df, feature_columns)
    X_valid, _, _ = _prepare_matrix(valid_df, feature_columns, feature_means, feature_stds)
    X_test, _, _ = _prepare_matrix(test_df, feature_columns, feature_means, feature_stds)

    y_train = pd.to_numeric(train_df[target_column], errors="coerce").to_numpy(dtype=float)
    y_valid = pd.to_numeric(valid_df[target_column], errors="coerce").to_numpy(dtype=float)
    y_test = pd.to_numeric(test_df[target_column], errors="coerce").to_numpy(dtype=float)

    if mode == "classification":
        weights, bias = _fit_logistic_regression(
            X_train,
            y_train,
            steps=num_steps,
            learning_rate=learning_rate,
            reg_strength=reg_strength,
        )
        valid_scores = _predict_logistic_regression(X_valid, weights, bias)
        test_scores = _predict_logistic_regression(X_test, weights, bias)
        train_scores = _predict_logistic_regression(X_train, weights, bias)
    else:
        weights, bias = _fit_ridge_regression(
            X_train,
            y_train,
            reg_strength=reg_strength,
        )
        valid_scores = _predict_linear_regression(X_valid, weights, bias)
        test_scores = _predict_linear_regression(X_test, weights, bias)
        train_scores = _predict_linear_regression(X_train, weights, bias)

    metrics = _evaluate_model(mode, y_train, train_scores, y_valid, valid_scores, y_test, test_scores)
    metrics["profile_name"] = profile_name

    predictions = _build_predictions(test_df, test_scores, mode, target_column, target_return_column)
    state = {
        "profile_name": profile_name,
        "mode": mode,
        "feature_columns": feature_columns,
        "target_column": target_column,
        "target_return_column": target_return_column,
        "feature_means": feature_means.tolist(),
        "feature_stds": feature_stds.tolist(),
        "weights": weights.tolist(),
        "bias": float(bias),
        "reg_strength": float(reg_strength),
        "learning_rate": float(learning_rate),
        "num_steps": int(num_steps),
    }
    return metrics, predictions, state


def _prepare_matrix(
    df: pd.DataFrame,
    feature_columns: list[str],
    means: np.ndarray | None = None,
    stds: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    working = df.copy()
    matrix = working[feature_columns].apply(pd.to_numeric, errors="coerce")
    if means is None or stds is None:
        means = matrix.mean(axis=0).fillna(0.0).to_numpy(dtype=float)
        means = np.nan_to_num(means, nan=0.0)
        stds = matrix.std(axis=0).replace(0.0, 1.0).fillna(1.0).to_numpy(dtype=float)
        stds = np.nan_to_num(stds, nan=1.0)
    else:
        means = np.nan_to_num(np.asarray(means, dtype=float), nan=0.0)
        stds = np.nan_to_num(np.asarray(stds, dtype=float), nan=1.0)
        stds = np.where(np.abs(stds) < 1e-12, 1.0, stds)
    filled = matrix.fillna(pd.Series(means, index=feature_columns))
    normalized = (filled.to_numpy(dtype=float) - means) / stds
    return normalized, means, stds


def _fit_ridge_regression(
    X: np.ndarray,
    y: np.ndarray,
    *,
    reg_strength: float,
) -> tuple[np.ndarray, float]:
    y = np.nan_to_num(y, nan=0.0)
    X_aug = np.c_[np.ones(len(X)), X]
    eye = np.eye(X_aug.shape[1], dtype=float)
    eye[0, 0] = 0.0
    gram = X_aug.T @ X_aug + reg_strength * eye
    rhs = X_aug.T @ y
    weights = np.linalg.solve(gram, rhs)
    return weights[1:], float(weights[0])


def _predict_linear_regression(X: np.ndarray, weights: np.ndarray, bias: float) -> np.ndarray:
    return X @ weights + bias


def _fit_logistic_regression(
    X: np.ndarray,
    y: np.ndarray,
    *,
    steps: int,
    learning_rate: float,
    reg_strength: float,
) -> tuple[np.ndarray, float]:
    y = np.nan_to_num(y, nan=0.0)
    y = np.clip(y, 0.0, 1.0)
    weights = np.zeros(X.shape[1], dtype=float)
    bias = 0.0
    n = max(len(X), 1)
    for _ in range(max(steps, 1)):
        logits = X @ weights + bias
        probs = _sigmoid(logits)
        error = probs - y
        grad_w = (X.T @ error) / n + reg_strength * weights
        grad_b = float(error.mean())
        weights -= learning_rate * grad_w
        bias -= learning_rate * grad_b
    return weights, bias


def _predict_logistic_regression(X: np.ndarray, weights: np.ndarray, bias: float) -> np.ndarray:
    return _sigmoid(X @ weights + bias)


def _evaluate_model(
    mode: str,
    y_train: np.ndarray,
    train_scores: np.ndarray,
    y_valid: np.ndarray,
    valid_scores: np.ndarray,
    y_test: np.ndarray,
    test_scores: np.ndarray,
) -> dict[str, Any]:
    if mode == "classification":
        metrics = {
            "train": classification_metrics(y_train.astype(int), train_scores),
            "valid": classification_metrics(y_valid.astype(int), valid_scores),
            "test": classification_metrics(y_test.astype(int), test_scores),
        }
    elif mode == "ranking":
        metrics = {
            "train": ranking_metrics(y_train, train_scores, y_train),
            "valid": ranking_metrics(y_valid, valid_scores, y_valid),
            "test": ranking_metrics(y_test, test_scores, y_test),
        }
    else:
        metrics = {
            "train": regression_metrics(y_train, train_scores),
            "valid": regression_metrics(y_valid, valid_scores),
            "test": regression_metrics(y_test, test_scores),
        }
    metrics["train_rows"] = int(len(y_train))
    metrics["valid_rows"] = int(len(y_valid))
    metrics["test_rows"] = int(len(y_test))
    return metrics


def _build_predictions(
    test_df: pd.DataFrame,
    scores: np.ndarray,
    mode: str,
    target_column: str,
    target_return_column: str,
) -> pd.DataFrame:
    prediction_columns = ["date", "symbol", "close"]
    for optional_column in ["amount", "turnover", "volume"]:
        if optional_column in test_df.columns:
            prediction_columns.append(optional_column)
    prediction_columns.append(target_return_column)
    if target_column != target_return_column:
        prediction_columns.append(target_column)

    predictions = test_df[prediction_columns].copy()
    if mode == "classification":
        predictions["pred_probability"] = scores
        predictions["pred_label"] = (predictions["pred_probability"] >= 0.5).astype(int)
    elif mode == "ranking":
        predictions["pred_score"] = scores
        predictions["pred_rank"] = (
            predictions.groupby("date")["pred_score"].rank(ascending=False, method="first")
        )
    else:
        predictions["pred_return"] = scores
    return predictions


def save_model_state(path: str | Path, state: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_model_state(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def score_frame(df: pd.DataFrame, state: dict[str, Any]) -> np.ndarray:
    feature_columns = list(state["feature_columns"])
    matrix = df[feature_columns].apply(pd.to_numeric, errors="coerce")
    means = np.asarray(state["feature_means"], dtype=float)
    stds = np.asarray(state["feature_stds"], dtype=float)
    stds = np.where(np.abs(stds) < 1e-12, 1.0, stds)
    filled = matrix.fillna(pd.Series(means, index=feature_columns))
    normalized = (filled.to_numpy(dtype=float) - means) / stds
    weights = np.asarray(state["weights"], dtype=float)
    bias = float(state["bias"])
    if state["mode"] == "classification":
        return _predict_logistic_regression(normalized, weights, bias)
    return _predict_linear_regression(normalized, weights, bias)


def prepare_base_frame(
    input_csv: str | Path,
    *,
    mode: str,
    horizon: int,
    threshold: float,
    eval_start: str = "",
    eval_end: str = "",
) -> tuple[pd.DataFrame, str, str]:
    raw_df = pd.read_csv(input_csv, encoding="utf-8-sig")
    normalized_df = normalize_dataframe(raw_df)
    feature_df = engineer_features(normalized_df)
    feature_df, target_column, target_return_column = add_targets(feature_df, mode, horizon, threshold)
    if eval_start:
        feature_df = feature_df[feature_df["date"] >= pd.to_datetime(eval_start)].copy()
    if eval_end:
        feature_df = feature_df[feature_df["date"] <= pd.to_datetime(eval_end)].copy()
    return feature_df, target_column, target_return_column


def choose_feature_columns(df: pd.DataFrame, extra_columns: list[str] | None = None) -> list[str]:
    features = list(select_feature_columns(df))
    if extra_columns:
        for column in extra_columns:
            if column in df.columns and column not in features:
                features.append(column)
    return features


def ensure_feature_columns(df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    working = df.copy()
    for column in feature_columns:
        if column not in working.columns:
            working[column] = neutral_fill_value(column)
    return working


def save_expert_artifacts(
    output_dir: str | Path,
    *,
    prepared_df: pd.DataFrame,
    metrics: dict[str, Any],
    predictions: pd.DataFrame,
    state: dict[str, Any],
    split_summary: dict[str, Any],
    input_csv: str,
    prepare_only: bool = False,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    prepared_path = output_path / "prepared_dataset.csv"
    metrics_path = output_path / "metrics.json"
    predictions_path = output_path / "test_predictions.csv"
    model_path = output_path / "model.json"
    feature_importance_path = output_path / "feature_importance.csv"

    prepared_to_save = prepared_df.copy()
    prepared_to_save["date"] = pd.to_datetime(prepared_to_save["date"]).dt.strftime("%Y-%m-%d")
    prepared_to_save.to_csv(prepared_path, index=False, encoding="utf-8")

    if not prepare_only:
        predictions_to_save = predictions.copy()
        predictions_to_save["date"] = pd.to_datetime(predictions_to_save["date"]).dt.strftime("%Y-%m-%d")
        predictions_to_save.to_csv(predictions_path, index=False, encoding="utf-8")
        save_model_state(model_path, state)
        importance_df = pd.DataFrame(
            {
                "feature": state["feature_columns"],
                "importance_abs": np.abs(np.asarray(state["weights"], dtype=float)),
                "importance_signed": np.asarray(state["weights"], dtype=float),
            }
        ).sort_values("importance_abs", ascending=False, kind="stable")
        importance_df.to_csv(feature_importance_path, index=False, encoding="utf-8")

    full_summary = {
        "input_csv": str(input_csv),
        "prepared_csv": str(prepared_path),
        "mode": state.get("mode"),
        "horizon": int(state.get("horizon", 0)),
        "threshold": float(state.get("threshold", 0.0)),
        "feature_columns": list(state.get("feature_columns", [])),
        "metrics": metrics,
        "state": state,
        "split_summary": split_summary,
    }
    metrics_path.write_text(json.dumps(full_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "prepared_path": str(prepared_path),
        "metrics_path": str(metrics_path),
        "predictions_path": str(predictions_path),
        "model_path": str(model_path),
        "feature_importance_path": str(feature_importance_path),
    }
