"""Shared utilities for the LSTM stock expert.

This module is intentionally self-contained so the LSTM package can be
developed and exercised without depending on other expert implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import random
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import torch
from torch import nn

from data_module.common.stock_schema import normalize_dataframe


PROFILE_NAME = "lstm"
DEFAULT_SEQUENCE_WINDOW = 20
DEFAULT_SEQUENCE_COLUMNS = [
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
    "amount_ma5_ratio",
]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.replace(0, np.nan)
    return numerator / denom


def _rolling_mean(grouped: pd.core.groupby.generic.SeriesGroupBy, window: int) -> pd.Series:
    return grouped.transform(lambda series: series.rolling(window, min_periods=window).mean())


def _rolling_std(grouped: pd.core.groupby.generic.SeriesGroupBy, window: int) -> pd.Series:
    return grouped.transform(lambda series: series.rolling(window, min_periods=window).std(ddof=0))


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create a richer feature set from normalized OHLCV data."""

    working = normalize_dataframe(df)
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"]).sort_values(["symbol", "date"], kind="stable").copy()

    for column in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
        if column in working.columns:
            working[column] = _to_numeric(working[column])

    grouped = working.groupby("symbol", group_keys=False)

    working["intraday_return"] = _safe_ratio(working["close"], working["open"]) - 1.0
    working["range_pct"] = _safe_ratio(working["high"], working["low"]) - 1.0
    working["return_1d"] = grouped["close"].pct_change(1)
    working["return_5d"] = grouped["close"].pct_change(5)
    working["return_10d"] = grouped["close"].pct_change(10)
    working["return_20d"] = grouped["close"].pct_change(20)

    for window in [5, 10, 20, 60]:
        ma = _rolling_mean(grouped["close"], window)
        working[f"close_ma{window}_gap"] = _safe_ratio(working["close"], ma) - 1.0

    for window in [5, 20]:
        ma = _rolling_mean(grouped["volume"], window)
        working[f"volume_ma{window}_ratio"] = _safe_ratio(working["volume"], ma)

    for window in [5, 10, 20]:
        working[f"volatility_{window}d"] = _rolling_std(grouped["return_1d"], window)

    high_20 = grouped["high"].transform(lambda series: series.rolling(20, min_periods=20).max())
    low_20 = grouped["low"].transform(lambda series: series.rolling(20, min_periods=20).min())
    working["breakout_20d"] = _safe_ratio(working["close"], high_20) - 1.0
    working["distance_to_low_20d"] = _safe_ratio(working["close"], low_20) - 1.0
    price_range_20 = (high_20 - low_20).replace(0, np.nan)
    working["price_position_20d"] = (working["close"] - low_20) / price_range_20

    volume_mean_20 = _rolling_mean(grouped["volume"], 20)
    volume_std_20 = _rolling_std(grouped["volume"], 20)
    working["volume_zscore_20d"] = (working["volume"] - volume_mean_20) / volume_std_20.replace(
        0, np.nan
    )

    if "amount" in working.columns:
        amount_ma_5 = _rolling_mean(grouped["amount"], 5)
        working["amount_ma5_ratio"] = _safe_ratio(working["amount"], amount_ma_5)
    else:
        working["amount_ma5_ratio"] = np.nan

    date_group = working.groupby("date", group_keys=False)
    working["market_return_1d"] = date_group["return_1d"].transform("mean")
    working["market_return_5d"] = date_group["return_5d"].transform("mean")
    working["relative_return_1d"] = working["return_1d"] - working["market_return_1d"]
    working["relative_return_5d"] = working["return_5d"] - working["market_return_5d"]
    working["cs_rank_return_1d"] = date_group["return_1d"].rank(pct=True, method="average")
    working["cs_rank_return_5d"] = date_group["return_5d"].rank(pct=True, method="average")
    working["cs_rank_return_20d"] = date_group["return_20d"].rank(pct=True, method="average")
    working["cs_rank_volume_ma5_ratio"] = date_group["volume_ma5_ratio"].rank(
        pct=True, method="average"
    )
    if "turnover" in working.columns:
        working["cs_rank_turnover"] = date_group["turnover"].rank(pct=True, method="average")
    else:
        working["cs_rank_turnover"] = np.nan

    working = working.replace([np.inf, -np.inf], np.nan)
    return working


def add_targets(
    df: pd.DataFrame,
    mode: str,
    horizon: int,
    threshold: float,
) -> tuple[pd.DataFrame, str, str]:
    """Attach forward-looking targets to the engineered frame."""

    working = df.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.sort_values(["symbol", "date"], kind="stable").copy()
    grouped = working.groupby("symbol", group_keys=False)
    target_return_column = f"target_return_{horizon}d"
    working[target_return_column] = grouped["close"].shift(-horizon) / working["close"] - 1.0

    if mode == "classification":
        target_column = f"target_up_{horizon}d"
        labels = (working[target_return_column] > threshold).astype(float)
        working[target_column] = labels.where(working[target_return_column].notna(), np.nan)
    else:
        target_column = target_return_column

    return working, target_column, target_return_column


def select_feature_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in DEFAULT_SEQUENCE_COLUMNS if column in df.columns]


def split_by_date(
    df: pd.DataFrame,
    train_ratio: float,
    valid_ratio: float,
    *,
    label_horizon: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    working = df.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"])

    unique_dates = sorted(working["date"].dt.strftime("%Y-%m-%d").unique())
    if len(unique_dates) < 20:
        raise ValueError("Need at least 20 unique dates after feature engineering to split safely.")

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

    date_str = working["date"].dt.strftime("%Y-%m-%d")
    train_df = working[date_str.isin(train_dates)].copy()
    valid_df = working[date_str.isin(valid_dates)].copy()
    test_df = working[date_str.isin(test_dates)].copy()

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
        "train_dates": sorted(train_dates),
        "valid_dates": sorted(valid_dates),
        "test_dates": sorted(test_dates),
    }
    return train_df, valid_df, test_df, summary


def auc_score(y_true: np.ndarray, y_score: np.ndarray) -> float | None:
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score).astype(float)
    positives = int((y_true == 1).sum())
    negatives = int((y_true == 0).sum())
    if positives == 0 or negatives == 0:
        return None

    ranks = pd.Series(y_score).rank(method="average").to_numpy()
    sum_positive_ranks = float(ranks[y_true == 1].sum())
    auc = (sum_positive_ranks - positives * (positives + 1) / 2.0) / (positives * negatives)
    return float(auc)


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if not mask.any():
        return {}

    y_true = y_true[mask]
    y_pred = y_pred[mask]
    residual = y_true - y_pred
    mse = float(np.mean(residual**2))
    rmse = float(math.sqrt(mse))
    mae = float(np.mean(np.abs(residual)))
    directional_accuracy = float(np.mean((y_true >= 0.0) == (y_pred >= 0.0)))
    if len(y_true) > 1 and np.std(y_true) > 0 and np.std(y_pred) > 0:
        pearson = float(np.corrcoef(y_true, y_pred)[0, 1])
    else:
        pearson = float("nan")
    return {
        "mse": mse,
        "rmse": rmse,
        "mae": mae,
        "directional_accuracy": directional_accuracy,
        "pearson_correlation": pearson,
    }


def classification_metrics(y_true: np.ndarray, y_score: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=int)
    y_score = np.asarray(y_score, dtype=float)
    mask = np.isfinite(y_score) & np.isfinite(y_true)
    if not mask.any():
        return {}

    y_true = y_true[mask]
    y_score = np.clip(y_score[mask], 1e-7, 1 - 1e-7)
    y_pred = (y_score >= 0.5).astype(int)

    tp = float(((y_pred == 1) & (y_true == 1)).sum())
    tn = float(((y_pred == 0) & (y_true == 0)).sum())
    fp = float(((y_pred == 1) & (y_true == 0)).sum())
    fn = float(((y_pred == 0) & (y_true == 1)).sum())
    accuracy = float((tp + tn) / max(len(y_true), 1))
    precision = float(tp / max(tp + fp, 1.0))
    recall = float(tp / max(tp + fn, 1.0))
    f1 = float(2.0 * precision * recall / max(precision + recall, 1e-12))
    logloss = float(-np.mean(y_true * np.log(y_score) + (1 - y_true) * np.log(1 - y_score)))
    auc = auc_score(y_true, y_score)

    metrics = {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "logloss": logloss,
    }
    if auc is not None:
        metrics["auc"] = auc
    return metrics


@dataclass
class FeatureNormalizer:
    columns: list[str]
    mean_: dict[str, float]
    scale_: dict[str, float]

    @classmethod
    def fit(cls, df: pd.DataFrame, columns: Sequence[str]) -> "FeatureNormalizer":
        mean_: dict[str, float] = {}
        scale_: dict[str, float] = {}
        for column in columns:
            values = _to_numeric(df[column]) if column in df.columns else pd.Series(dtype=float)
            values = values.replace([np.inf, -np.inf], np.nan).dropna()
            if values.empty:
                mean = 0.0
                scale = 1.0
            else:
                mean = float(values.mean())
                scale = float(values.std(ddof=0))
                if not np.isfinite(scale) or scale == 0.0:
                    scale = 1.0
            mean_[column] = mean
            scale_[column] = scale
        return cls(columns=list(columns), mean_=mean_, scale_=scale_)

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        working = df.copy()
        for column in self.columns:
            mean = self.mean_.get(column, 0.0)
            scale = self.scale_.get(column, 1.0)
            if column in working.columns:
                values = _to_numeric(working[column])
            else:
                values = pd.Series(np.nan, index=working.index, dtype=float)
            working[column] = ((values.fillna(mean) - mean) / scale).astype(float)
        return working

    def to_dict(self) -> dict[str, object]:
        return {
            "columns": list(self.columns),
            "mean": self.mean_,
            "scale": self.scale_,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "FeatureNormalizer":
        return cls(
            columns=list(payload.get("columns", [])),
            mean_={str(k): float(v) for k, v in dict(payload.get("mean", {})).items()},
            scale_={str(k): float(v) for k, v in dict(payload.get("scale", {})).items()},
        )


def build_sequence_samples(
    df: pd.DataFrame,
    feature_columns: Sequence[str],
    seq_len: int,
    target_column: str,
    *,
    target_return_column: str = "",
    extra_columns: Sequence[str] | None = None,
    include_missing_target: bool = False,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    working = df.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"]).sort_values(["symbol", "date"], kind="stable").copy()

    extra_columns = list(extra_columns or [])
    meta_columns = ["date", "symbol", "close"]
    for column in ["amount", "turnover", "volume"]:
        if column in working.columns:
            meta_columns.append(column)
    if target_return_column and target_return_column in working.columns:
        meta_columns.append(target_return_column)
    if target_column in working.columns and target_column not in meta_columns:
        meta_columns.append(target_column)
    for column in extra_columns:
        if column in working.columns and column not in meta_columns:
            meta_columns.append(column)

    samples: list[np.ndarray] = []
    targets: list[float] = []
    metadata: list[dict[str, object]] = []

    for symbol, group in working.groupby("symbol", sort=False):
        group = group.sort_values("date", kind="stable").reset_index(drop=True)
        if len(group) < seq_len:
            continue

        feature_block = group.loc[:, list(feature_columns)].to_numpy(dtype=float)
        target_block = pd.to_numeric(group[target_column], errors="coerce").to_numpy(dtype=float)

        for end_index in range(seq_len - 1, len(group)):
            window = feature_block[end_index - seq_len + 1 : end_index + 1]
            if not np.isfinite(window).all():
                continue
            target_value = target_block[end_index]
            if not include_missing_target and not np.isfinite(target_value):
                continue

            samples.append(window.astype(np.float32, copy=False))
            targets.append(float(target_value) if np.isfinite(target_value) else float("nan"))
            row = group.loc[end_index, meta_columns].to_dict()
            row["sequence_length"] = int(seq_len)
            row["symbol"] = str(row.get("symbol", symbol))
            metadata.append(row)

    if not samples:
        return (
            np.empty((0, seq_len, len(feature_columns)), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
            pd.DataFrame(columns=meta_columns + ["sequence_length"]),
        )

    X = np.stack(samples, axis=0).astype(np.float32, copy=False)
    y = np.asarray(targets, dtype=np.float32)
    meta = pd.DataFrame(metadata)
    meta["date"] = pd.to_datetime(meta["date"], errors="coerce")
    return X, y, meta


class SequenceLSTM(nn.Module):
    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_layers: int,
        dropout: float,
        output_dim: int = 1,
    ) -> None:
        super().__init__()
        lstm_dropout = dropout if num_layers > 1 else 0.0
        self.encoder = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=lstm_dropout,
        )
        head_hidden = max(32, hidden_size // 2)
        self.norm = nn.LayerNorm(hidden_size)
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size, head_hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(head_hidden, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        encoded, _ = self.encoder(x)
        last_state = encoded[:, -1, :]
        normalized = self.norm(last_state)
        return self.head(normalized)


def build_lstm_model(
    input_size: int,
    hidden_size: int,
    num_layers: int,
    dropout: float,
    mode: str,
) -> nn.Module:
    output_dim = 1
    model = SequenceLSTM(
        input_size=input_size,
        hidden_size=hidden_size,
        num_layers=num_layers,
        dropout=dropout,
        output_dim=output_dim,
    )
    return model


def run_model_in_batches(
    model: nn.Module,
    X: np.ndarray,
    *,
    batch_size: int = 256,
    device: str = "cpu",
) -> np.ndarray:
    if len(X) == 0:
        return np.empty((0,), dtype=np.float32)

    model = model.to(device)
    model.eval()
    outputs: list[np.ndarray] = []

    with torch.no_grad():
        for start in range(0, len(X), batch_size):
            batch = torch.as_tensor(X[start : start + batch_size], dtype=torch.float32, device=device)
            logits = model(batch)
            outputs.append(logits.detach().cpu().numpy().reshape(-1))

    return np.concatenate(outputs, axis=0).astype(np.float32, copy=False)


def build_checkpoint_payload(
    *,
    model: nn.Module,
    config: dict[str, object],
    normalizer: FeatureNormalizer,
    feature_columns: Sequence[str],
    target_column: str,
    target_return_column: str,
    mode: str,
) -> dict[str, object]:
    return {
        "profile_name": PROFILE_NAME,
        "mode": mode,
        "config": dict(config),
        "feature_columns": list(feature_columns),
        "target_column": target_column,
        "target_return_column": target_return_column,
        "normalizer": normalizer.to_dict(),
        "model_state_dict": model.state_dict(),
    }


def save_checkpoint(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, path)


def load_checkpoint(path: Path, map_location: str = "cpu") -> dict[str, object]:
    return torch.load(path, map_location=map_location)


def load_config(source: dict[str, object] | Path) -> dict[str, object]:
    if isinstance(source, Path):
        payload = load_checkpoint(source)
    else:
        payload = source
    config = payload.get("config")
    if not isinstance(config, dict):
        raise ValueError("Checkpoint does not contain a config payload.")
    return config


def build_default_config(
    *,
    mode: str,
    horizon: int,
    threshold: float,
    seq_len: int,
    hidden_size: int,
    num_layers: int,
    dropout: float,
    batch_size: int,
    epochs: int,
    lr: float,
    weight_decay: float,
    patience: int,
    seed: int,
    train_ratio: float,
    valid_ratio: float,
) -> dict[str, object]:
    return {
        "mode": mode,
        "horizon": horizon,
        "threshold": threshold,
        "seq_len": seq_len,
        "hidden_size": hidden_size,
        "num_layers": num_layers,
        "dropout": dropout,
        "batch_size": batch_size,
        "epochs": epochs,
        "lr": lr,
        "weight_decay": weight_decay,
        "patience": patience,
        "seed": seed,
        "train_ratio": train_ratio,
        "valid_ratio": valid_ratio,
    }
