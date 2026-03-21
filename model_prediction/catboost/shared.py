"""Shared helpers for the CatBoost-compatible expert module.

This module intentionally stays dependency-light while keeping the same
artifact contract as the LightGBM module. It reuses the feature engineering
and time split helpers from the LightGBM implementation so the downstream
white-box risk layer can consume the same `test_predictions.csv` format.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

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


DEFAULT_CATEGORICAL_COLUMNS = [
    "symbol",
    "industry_group",
    "sector",
    "market_segment",
    "board",
    "exchange",
]


def output_dir_for(project_root: Path, module_name: str, args: Any) -> Path:
    if getattr(args, "output_dir", ""):
        return Path(args.output_dir)
    input_stem = Path(args.input_csv).stem
    run_name = f"{input_stem}_{args.mode}_{args.horizon}d"
    return project_root / "model_prediction" / module_name / "artifacts" / run_name


def neutral_fill_value(column: str) -> float:
    if column.startswith("cs_rank_") or column.endswith("_target_mean"):
        return 0.5
    if "price_position" in column:
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


def prepare_base_frame(
    input_csv: str | Path,
    *,
    mode: str,
    horizon: int,
    threshold: float,
) -> tuple[pd.DataFrame, str, str]:
    raw_df = pd.read_csv(input_csv, encoding="utf-8-sig")
    normalized_df = normalize_dataframe(raw_df)
    feature_df = engineer_features(normalized_df)
    feature_df, target_column, target_return_column = add_targets(
        feature_df,
        mode,
        horizon,
        threshold,
    )
    return feature_df, target_column, target_return_column


def encode_categorical_targets(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    test_df: pd.DataFrame,
    *,
    target_column: str,
    categorical_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], list[str]]:
    working_columns = categorical_columns or DEFAULT_CATEGORICAL_COLUMNS
    available_columns = [column for column in working_columns if column in train_df.columns]
    if not available_columns:
        return train_df, valid_df, test_df, {
            "global_mean": float(pd.to_numeric(train_df[target_column], errors="coerce").mean()),
            "categorical_columns": [],
            "encodings": {},
        }, []

    global_mean = float(pd.to_numeric(train_df[target_column], errors="coerce").mean())
    encoding_state: dict[str, Any] = {
        "global_mean": global_mean,
        "categorical_columns": available_columns,
        "encodings": {},
    }

    def _encode_frame(frame: pd.DataFrame) -> pd.DataFrame:
        merged = frame.copy()
        for column in available_columns:
            stats = (
                train_df.groupby(column)[target_column]
                .agg(["mean", "size"])
                .rename(columns={"mean": f"{column}_target_mean", "size": f"{column}_count"})
                .reset_index()
            )
            stats[column] = stats[column].astype(str)
            merged[column] = merged[column].astype(str)
            merged = merged.merge(stats, on=column, how="left")
            merged[f"{column}_target_mean"] = merged[f"{column}_target_mean"].fillna(global_mean)
            merged[f"{column}_count"] = merged[f"{column}_count"].fillna(0.0)
            encoding_state["encodings"][column] = stats.to_dict(orient="records")
        return merged

    return _encode_frame(train_df), _encode_frame(valid_df), _encode_frame(test_df), encoding_state, [
        f"{column}_target_mean" for column in available_columns
    ] + [f"{column}_count" for column in available_columns]


def apply_categorical_encoding_from_state(
    df: pd.DataFrame,
    state: dict[str, Any],
) -> pd.DataFrame:
    encoding_state = state.get("categorical_encoding", {})
    categorical_columns = list(encoding_state.get("categorical_columns", []))
    encodings = encoding_state.get("encodings", {})
    global_mean = float(encoding_state.get("global_mean", 0.0))

    working = df.copy()
    for column in categorical_columns:
        if column not in working.columns:
            working[column] = ""
        working[column] = working[column].astype(str)
        stats_rows = list(encodings.get(column, []))
        if not stats_rows:
            working[f"{column}_target_mean"] = global_mean
            working[f"{column}_count"] = 0.0
            continue

        stats = pd.DataFrame(stats_rows)
        stats[column] = stats[column].astype(str)
        working = working.merge(stats, on=column, how="left")
        working[f"{column}_target_mean"] = working[f"{column}_target_mean"].fillna(global_mean)
        working[f"{column}_count"] = working[f"{column}_count"].fillna(0.0)
    return working


def choose_feature_columns(df: pd.DataFrame, *, extra_columns: list[str] | None = None) -> list[str]:
    features = [column for column in select_feature_columns(df) if column in df.columns]
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
    working[feature_columns] = working[feature_columns].apply(pd.to_numeric, errors="coerce")
    for column in feature_columns:
        working[column] = working[column].fillna(neutral_fill_value(column))
    return working


def _prepare_matrix(
    df: pd.DataFrame,
    feature_columns: list[str],
    means: np.ndarray | None = None,
    stds: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    matrix = df[feature_columns].apply(pd.to_numeric, errors="coerce")
    if means is None or stds is None:
        means = np.nan_to_num(matrix.mean(axis=0).to_numpy(dtype=float), nan=0.0)
        stds = matrix.std(axis=0).replace(0.0, 1.0).fillna(1.0).to_numpy(dtype=float)
        stds = np.nan_to_num(stds, nan=1.0)
        stds = np.where(np.abs(stds) < 1e-12, 1.0, stds)
    else:
        means = np.nan_to_num(np.asarray(means, dtype=float), nan=0.0)
        stds = np.nan_to_num(np.asarray(stds, dtype=float), nan=1.0)
        stds = np.where(np.abs(stds) < 1e-12, 1.0, stds)

    filled = matrix.fillna(pd.Series(means, index=feature_columns))
    normalized = (filled.to_numpy(dtype=float) - means) / stds
    return normalized, means, stds


def _sigmoid(x: np.ndarray) -> np.ndarray:
    clipped = np.clip(x, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _fit_ridge_regression(X: np.ndarray, y: np.ndarray, *, reg_strength: float) -> tuple[np.ndarray, float]:
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


def _evaluate_model(
    mode: str,
    y_train: np.ndarray,
    train_scores: np.ndarray,
    y_valid: np.ndarray,
    valid_scores: np.ndarray,
    y_test: np.ndarray,
    test_scores: np.ndarray,
    y_test_return: np.ndarray,
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
            "test": ranking_metrics(y_test, test_scores, y_test_return),
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
        predictions["pred_rank"] = predictions.groupby("date")["pred_score"].rank(
            ascending=False, method="first"
        )
    else:
        predictions["pred_return"] = scores
    return predictions


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
    y_test_return = pd.to_numeric(test_df[target_return_column], errors="coerce").to_numpy(dtype=float)

    if mode == "classification":
        weights, bias = _fit_logistic_regression(
            X_train,
            y_train,
            steps=num_steps,
            learning_rate=learning_rate,
            reg_strength=reg_strength,
        )
        train_scores = _predict_linear_regression(X_train, weights, bias)
        valid_scores = _predict_linear_regression(X_valid, weights, bias)
        test_scores = _predict_linear_regression(X_test, weights, bias)
        train_scores = _sigmoid(train_scores)
        valid_scores = _sigmoid(valid_scores)
        test_scores = _sigmoid(test_scores)
    else:
        weights, bias = _fit_ridge_regression(
            X_train,
            y_train,
            reg_strength=reg_strength,
        )
        train_scores = _predict_linear_regression(X_train, weights, bias)
        valid_scores = _predict_linear_regression(X_valid, weights, bias)
        test_scores = _predict_linear_regression(X_test, weights, bias)

    metrics = _evaluate_model(
        mode,
        y_train,
        train_scores,
        y_valid,
        valid_scores,
        y_test,
        test_scores,
        y_test_return,
    )
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
    scores = _predict_linear_regression(normalized, weights, bias)
    if state["mode"] == "classification":
        return _sigmoid(scores)
    return scores


def save_expert_artifacts(
    output_dir: Path,
    *,
    prepared_df: pd.DataFrame,
    metrics: dict[str, Any],
    predictions: pd.DataFrame | None,
    state: dict[str, Any],
    split_summary: dict[str, Any],
    input_csv: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = output_dir / "prepared_dataset.csv"
    prepared_to_save = prepared_df.copy()
    if "date" in prepared_to_save.columns:
        prepared_to_save["date"] = pd.to_datetime(prepared_to_save["date"]).dt.strftime("%Y-%m-%d")
    prepared_to_save.to_csv(prepared_path, index=False, encoding="utf-8")

    feature_columns = list(state.get("feature_columns", []))
    feature_importance = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance": np.abs(np.asarray(state.get("weights", []), dtype=float)),
        }
    )
    feature_importance["importance_pct"] = (
        feature_importance["importance"] / feature_importance["importance"].sum()
        if not feature_importance.empty and feature_importance["importance"].sum() else 0.0
    )
    feature_importance = feature_importance.sort_values("importance", ascending=False, kind="stable")

    metrics_payload = {
        "input_csv": input_csv,
        "mode": state.get("mode"),
        "horizon": int(state.get("horizon", 0)),
        "threshold": float(state.get("threshold", 0.0)),
        "feature_columns": feature_columns,
        "split_summary": split_summary,
        "metrics": metrics,
        "state": {
            key: value
            for key, value in state.items()
            if key not in {"weights", "feature_means", "feature_stds"}
        },
    }
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    model_path = output_dir / "model.json"
    save_model_state(model_path, state)

    predictions_path = output_dir / "test_predictions.csv"
    if predictions is not None:
        predictions_to_save = predictions.copy()
        if "date" in predictions_to_save.columns:
            predictions_to_save["date"] = pd.to_datetime(predictions_to_save["date"]).dt.strftime(
                "%Y-%m-%d"
            )
        predictions_to_save.to_csv(predictions_path, index=False, encoding="utf-8")

    feature_importance_path = output_dir / "feature_importance.csv"
    feature_importance.to_csv(feature_importance_path, index=False, encoding="utf-8")

    return {
        "prepared_path": prepared_path,
        "metrics_path": metrics_path,
        "predictions_path": predictions_path,
        "model_path": model_path,
        "feature_importance_path": feature_importance_path,
    }
