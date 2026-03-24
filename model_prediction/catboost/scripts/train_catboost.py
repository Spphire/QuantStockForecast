#!/usr/bin/env python3
"""Train a real CatBoost stock expert on the shared normalized schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_prediction.catboost.shared import (
    DEFAULT_CATEGORICAL_COLUMNS,
    add_calendar_features,
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
        description="Train a CatBoost stock model or prepare an aligned dataset."
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


def available_categorical_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in DEFAULT_CATEGORICAL_COLUMNS if column in df.columns]


def prepare_model_frame(
    df: pd.DataFrame,
    *,
    feature_columns: list[str],
    categorical_columns: list[str],
) -> pd.DataFrame:
    working = df.copy()
    for column in feature_columns:
        if column not in working.columns:
            if column in categorical_columns:
                working[column] = "UNKNOWN"
            else:
                working[column] = 0.0

    for column in categorical_columns:
        working[column] = working[column].fillna("UNKNOWN").astype(str)

    numeric_columns = [column for column in feature_columns if column not in categorical_columns]
    if numeric_columns:
        working[numeric_columns] = working[numeric_columns].apply(pd.to_numeric, errors="coerce")
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


def build_pool(
    catboost_module,
    df: pd.DataFrame,
    *,
    feature_columns: list[str],
    categorical_columns: list[str],
    label_column: str,
    ranking: bool,
):
    feature_frame = prepare_model_frame(
        df,
        feature_columns=feature_columns,
        categorical_columns=categorical_columns,
    )[feature_columns]
    group_id = None
    if ranking:
        group_id = pd.factorize(df["date"].dt.strftime("%Y-%m-%d"), sort=True)[0]
    return catboost_module.Pool(
        data=feature_frame,
        label=df[label_column].to_numpy(),
        cat_features=categorical_columns,
        group_id=group_id,
    )


def save_feature_importance(model, pool, feature_columns: list[str], output_dir: Path) -> Path:
    importance = model.get_feature_importance(pool, type="FeatureImportance")
    importance_df = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance": importance,
        }
    ).sort_values("importance", ascending=False, kind="stable")
    path = output_dir / "feature_importance.csv"
    importance_df.to_csv(path, index=False, encoding="utf-8")
    return path


def train_catboost(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    test_df: pd.DataFrame,
    *,
    feature_columns: list[str],
    categorical_columns: list[str],
    target_column: str,
    target_return_column: str,
    mode: str,
    num_boost_round: int,
    output_dir: Path,
) -> tuple[dict[str, object], pd.DataFrame, Path, Path]:
    try:
        import catboost
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "catboost is not installed. Install project dependencies or rerun with --prepare-only."
        ) from exc

    ranking = mode == "ranking"
    train_pool = build_pool(
        catboost,
        train_df,
        feature_columns=feature_columns,
        categorical_columns=categorical_columns,
        label_column=target_column,
        ranking=ranking,
    )
    valid_pool = build_pool(
        catboost,
        valid_df,
        feature_columns=feature_columns,
        categorical_columns=categorical_columns,
        label_column=target_column,
        ranking=ranking,
    )
    test_pool = build_pool(
        catboost,
        test_df,
        feature_columns=feature_columns,
        categorical_columns=categorical_columns,
        label_column=target_column,
        ranking=ranking,
    )

    common_kwargs = {
        "iterations": num_boost_round,
        "learning_rate": 0.05,
        "depth": 6,
        "random_seed": 42,
        "allow_writing_files": False,
        "verbose": False,
    }
    if mode == "classification":
        model = catboost.CatBoostClassifier(
            loss_function="Logloss",
            eval_metric="AUC",
            **common_kwargs,
        )
    elif mode == "ranking":
        model = catboost.CatBoostRanker(
            loss_function="YetiRankPairwise",
            eval_metric="NDCG:top=10",
            **common_kwargs,
        )
    else:
        model = catboost.CatBoostRegressor(
            loss_function="RMSE",
            eval_metric="RMSE",
            **common_kwargs,
        )

    model.fit(train_pool, eval_set=valid_pool, use_best_model=True)

    if mode == "classification":
        test_scores = model.predict_proba(test_pool)[:, 1]
    else:
        test_scores = model.predict(test_pool)

    predictions = test_df[base_prediction_columns(test_df, target_return_column, target_column)].copy()
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

    model_path = output_dir / "model.cbm"
    model.save_model(str(model_path))
    importance_path = save_feature_importance(model, test_pool, feature_columns, output_dir)
    best_iteration = int(model.get_best_iteration())
    metrics["best_iteration"] = best_iteration + 1 if best_iteration >= 0 else num_boost_round
    metrics["model_path"] = str(model_path)
    return metrics, predictions, model_path, importance_path


def main() -> int:
    args = parse_args()
    output_dir = output_dir_for(PROJECT_ROOT, "catboost", args)
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
        feature_df, calendar_columns = add_calendar_features(feature_df)
        feature_df = feature_df.sort_values(["date", "symbol"], kind="stable").copy()
        categorical_columns = available_categorical_columns(feature_df)
        numeric_features = choose_feature_columns(feature_df, extra_columns=calendar_columns)
        feature_columns = list(dict.fromkeys(numeric_features + categorical_columns))
        if not feature_columns:
            raise ValueError("No feature columns were generated.")
        prepared_df = feature_df.dropna(subset=[target_column, target_return_column]).copy()
        train_df, valid_df, test_df, split_summary = split_by_date(
            prepared_df, args.train_ratio, args.valid_ratio, label_horizon=args.horizon
        )
    except Exception as exc:
        print(f"[ERROR] Failed to prepare training data: {exc}")
        return 1

    prepared_to_save = prepared_df.copy()
    prepared_to_save["date"] = pd.to_datetime(prepared_to_save["date"]).dt.strftime("%Y-%m-%d")
    prepared_path = output_dir / "prepared_dataset.csv"
    prepared_to_save.to_csv(prepared_path, index=False, encoding="utf-8")

    summary = {
        "input_csv": str(input_path),
        "prepared_csv": str(prepared_path),
        "mode": args.mode,
        "horizon": args.horizon,
        "threshold": args.threshold,
        "symbol_count": int(prepared_df["symbol"].nunique()),
        "feature_columns": feature_columns,
        "categorical_features": categorical_columns,
        "target_column": target_column,
        "target_return_column": target_return_column,
        "split_summary": split_summary,
        "expert_name": "catboost",
    }

    if args.prepare_only:
        summary_path = output_dir / "prepare_summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Prepared dataset: {prepared_path}")
        print(f"[INFO] Feature count: {len(feature_columns)}")
        print(f"[INFO] Target column: {target_column}")
        return 0

    try:
        metrics, predictions, model_path, importance_path = train_catboost(
            train_df,
            valid_df,
            test_df,
            feature_columns=feature_columns,
            categorical_columns=categorical_columns,
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
