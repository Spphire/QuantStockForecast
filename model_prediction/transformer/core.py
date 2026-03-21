"""Shared implementation for the lightweight Transformer stock expert."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Iterable, Sequence

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
)

PROFILE_NAME = "transformer"
DEFAULT_SEQUENCE_WINDOW = 40
DEFAULT_SEQUENCE_COLUMNS = [
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "close_ma20_gap",
    "volume_ma5_ratio",
    "volatility_20d",
    "market_return_1d",
    "market_return_5d",
    "relative_return_1d",
    "relative_return_5d",
    "cs_rank_return_1d",
    "cs_rank_return_5d",
    "price_position_20d",
    "volume_zscore_20d",
]


try:  # pragma: no cover - torch is not available in the current environment
    import torch  # type: ignore
    import torch.nn as nn  # type: ignore
    from torch.utils.data import DataLoader, TensorDataset  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    DataLoader = None  # type: ignore[assignment]
    TensorDataset = None  # type: ignore[assignment]


def require_torch():
    """Import torch lazily and raise a clear error if it is unavailable."""

    if torch is None:  # pragma: no cover - depends on environment
        raise ModuleNotFoundError(
            "PyTorch is not installed. Install torch before running transformer training or inference."
        )
    return torch


def output_dir_for(
    input_csv: str | Path,
    mode: str,
    horizon: int,
    lookback: int,
    requested_output_dir: str | Path = "",
) -> Path:
    if str(requested_output_dir).strip():
        return Path(requested_output_dir)
    input_stem = Path(input_csv).stem
    run_name = f"{input_stem}_{mode}_{horizon}d_lb{lookback}"
    return Path(__file__).resolve().parent / "artifacts" / run_name


def _as_frame(input_csv: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(input_csv, pd.DataFrame):
        return input_csv.copy()
    return pd.read_csv(Path(input_csv), encoding="utf-8-sig")


def _coerce_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _fill_value_for_feature(column: str) -> float:
    if column.startswith("cs_rank_") or "price_position" in column:
        return 0.5
    return 0.0


def _safe_std(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return 1.0
    std = float(np.nanstd(array))
    if not np.isfinite(std) or std <= 1e-12:
        return 1.0
    return std


def _safe_mean(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        return 0.0
    mean = float(np.nanmean(array))
    if not np.isfinite(mean):
        return 0.0
    return mean


def load_and_prepare_frame(
    input_csv: str | Path | pd.DataFrame,
    *,
    mode: str,
    horizon: int,
    threshold: float,
    eval_start: str = "",
    eval_end: str = "",
    reference_feature_columns: Sequence[str] | None = None,
    require_target: bool = True,
) -> tuple[pd.DataFrame, str, str, list[str], dict[str, float]]:
    """Load a normalized CSV and prepare aligned transformer features and targets."""

    raw_df = _as_frame(input_csv)
    normalized_df = normalize_dataframe(raw_df)
    feature_df = engineer_features(normalized_df)
    feature_df, target_column, target_return_column = add_targets(feature_df, mode, horizon, threshold)

    working = feature_df.copy()
    if eval_start:
        working = working[working["date"] >= pd.to_datetime(eval_start)].copy()
    if eval_end:
        working = working[working["date"] <= pd.to_datetime(eval_end)].copy()

    if reference_feature_columns is None:
        feature_columns = select_feature_columns(working)
    else:
        feature_columns = list(reference_feature_columns)

    if not feature_columns:
        raise ValueError("No feature columns were identified for transformer training.")

    filled_missing_features: dict[str, float] = {}
    for column in feature_columns:
        if column not in working.columns:
            fill_value = _fill_value_for_feature(column)
            working[column] = fill_value
            filled_missing_features[column] = fill_value

    for column in feature_columns:
        working[column] = _coerce_series(working[column])

    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"]).sort_values(["symbol", "date"], kind="stable").copy()

    if require_target:
        working = working.dropna(subset=[target_column]).copy()

    return working.reset_index(drop=True), target_column, target_return_column, feature_columns, filled_missing_features


def split_unique_dates(
    df: pd.DataFrame, train_ratio: float, valid_ratio: float
) -> tuple[set[str], set[str], set[str], dict[str, object]]:
    unique_dates = sorted(df["date"].dt.strftime("%Y-%m-%d").unique())
    if len(unique_dates) < 20:
        raise ValueError("Need at least 20 unique dates to create stable train/valid/test splits.")

    train_cut = max(1, int(len(unique_dates) * train_ratio))
    valid_cut = max(train_cut + 1, int(len(unique_dates) * (train_ratio + valid_ratio)))
    valid_cut = min(valid_cut, len(unique_dates) - 1)

    train_dates = set(unique_dates[:train_cut])
    valid_dates = set(unique_dates[train_cut:valid_cut])
    test_dates = set(unique_dates[valid_cut:])
    if not train_dates or not valid_dates or not test_dates:
        raise ValueError("Time split failed. Adjust ratios or provide a longer date range.")

    summary = {
        "train_rows": int(df[df["date"].dt.strftime("%Y-%m-%d").isin(train_dates)].shape[0]),
        "valid_rows": int(df[df["date"].dt.strftime("%Y-%m-%d").isin(valid_dates)].shape[0]),
        "test_rows": int(df[df["date"].dt.strftime("%Y-%m-%d").isin(test_dates)].shape[0]),
        "train_symbols": int(df[df["date"].dt.strftime("%Y-%m-%d").isin(train_dates)]["symbol"].nunique()),
        "valid_symbols": int(df[df["date"].dt.strftime("%Y-%m-%d").isin(valid_dates)]["symbol"].nunique()),
        "test_symbols": int(df[df["date"].dt.strftime("%Y-%m-%d").isin(test_dates)]["symbol"].nunique()),
        "train_date_min": min(train_dates),
        "train_date_max": max(train_dates),
        "valid_date_min": min(valid_dates),
        "valid_date_max": max(valid_dates),
        "test_date_min": min(test_dates),
        "test_date_max": max(test_dates),
    }
    return train_dates, valid_dates, test_dates, summary


def split_frame_by_dates(
    df: pd.DataFrame, train_dates: set[str], valid_dates: set[str], test_dates: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    date_strings = df["date"].dt.strftime("%Y-%m-%d")
    train_df = df[date_strings.isin(train_dates)].copy()
    valid_df = df[date_strings.isin(valid_dates)].copy()
    test_df = df[date_strings.isin(test_dates)].copy()
    return train_df, valid_df, test_df


def fit_feature_scaler(train_df: pd.DataFrame, feature_columns: Sequence[str]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for column in feature_columns:
        values = _coerce_series(train_df[column])
        mean = _safe_mean(values)
        std = _safe_std(values)
        stats[column] = {"mean": mean, "std": std}
    return stats


def apply_feature_scaler(
    df: pd.DataFrame, feature_columns: Sequence[str], feature_stats: dict[str, dict[str, float]]
) -> pd.DataFrame:
    working = df.copy()
    for column in feature_columns:
        if column not in working.columns:
            working[column] = feature_stats.get(column, {}).get("mean", 0.0)
        values = _coerce_series(working[column])
        mean = float(feature_stats.get(column, {}).get("mean", 0.0))
        std = float(feature_stats.get(column, {}).get("std", 1.0))
        if not np.isfinite(std) or std <= 1e-12:
            std = 1.0
        working[column] = (values.fillna(mean) - mean) / std
    return working


def target_scaler_stats(train_df: pd.DataFrame, target_column: str, mode: str) -> dict[str, float]:
    values = _coerce_series(train_df[target_column]).to_numpy(dtype=float)
    if mode == "classification":
        return {"mean": 0.0, "std": 1.0}
    if mode == "ranking":
        mean = _safe_mean(values)
        std = _safe_std(values)
        return {"mean": mean, "std": std}
    mean = _safe_mean(values)
    std = _safe_std(values)
    return {"mean": mean, "std": std}


def transform_target(values: np.ndarray | pd.Series, *, mode: str, target_stats: dict[str, float] | None) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if mode == "classification":
        return array.astype(np.float32)
    if not target_stats:
        return array.astype(np.float32)
    mean = float(target_stats.get("mean", 0.0))
    std = float(target_stats.get("std", 1.0))
    if not np.isfinite(std) or std <= 1e-12:
        std = 1.0
    return ((array - mean) / std).astype(np.float32)


def inverse_target(values: np.ndarray | pd.Series, *, mode: str, target_stats: dict[str, float] | None) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if mode == "classification":
        return array.astype(np.float32)
    if not target_stats:
        return array.astype(np.float32)
    mean = float(target_stats.get("mean", 0.0))
    std = float(target_stats.get("std", 1.0))
    if not np.isfinite(std) or std <= 1e-12:
        std = 1.0
    return (array * std + mean).astype(np.float32)


def build_sequence_samples(
    df: pd.DataFrame,
    feature_columns: Sequence[str],
    target_column: str,
    target_return_column: str,
    lookback: int,
    *,
    mode: str,
    target_stats: dict[str, float] | None = None,
    include_missing_target: bool = False,
) -> tuple[np.ndarray, pd.DataFrame, np.ndarray, np.ndarray]:
    if lookback <= 0:
        raise ValueError("lookback must be positive.")

    working = df.sort_values(["symbol", "date"], kind="stable").copy()
    samples: list[np.ndarray] = []
    meta_rows: list[pd.Series] = []
    target_values: list[float] = []
    target_return_values: list[float] = []

    for _, symbol_frame in working.groupby("symbol", sort=False):
        symbol_frame = symbol_frame.reset_index(drop=True)
        if len(symbol_frame) < lookback:
            continue

        feature_matrix = symbol_frame[list(feature_columns)].to_numpy(dtype=np.float32)
        target_series = _coerce_series(symbol_frame[target_column]).to_numpy(dtype=float)
        target_return_series = _coerce_series(symbol_frame[target_return_column]).to_numpy(dtype=float)

        for end_idx in range(lookback - 1, len(symbol_frame)):
            window = feature_matrix[end_idx - lookback + 1 : end_idx + 1]
            if window.shape != (lookback, len(feature_columns)):
                continue
            if not np.isfinite(window).all():
                continue

            target_value = target_series[end_idx]
            target_return_value = target_return_series[end_idx]
            if not include_missing_target and (not np.isfinite(target_value) or not np.isfinite(target_return_value)):
                continue

            samples.append(window.astype(np.float32))
            meta_rows.append(symbol_frame.iloc[end_idx].copy())
            if mode == "classification":
                target_values.append(float(target_value) if np.isfinite(target_value) else np.nan)
            else:
                target_values.append(
                    float(transform_target(np.asarray([target_value]), mode=mode, target_stats=target_stats)[0])
                    if np.isfinite(target_value)
                    else np.nan
                )
            target_return_values.append(float(target_return_value) if np.isfinite(target_return_value) else np.nan)

    if not samples:
        return (
            np.empty((0, lookback, len(feature_columns)), dtype=np.float32),
            pd.DataFrame(),
            np.empty((0,), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
        )

    sample_meta = pd.DataFrame(meta_rows).reset_index(drop=True)
    sample_meta["date"] = pd.to_datetime(sample_meta["date"], errors="coerce")
    return (
        np.asarray(samples, dtype=np.float32),
        sample_meta,
        np.asarray(target_values, dtype=np.float32),
        np.asarray(target_return_values, dtype=np.float32),
    )


def sequence_indices_for_dates(sample_meta: pd.DataFrame, dates: Iterable[str]) -> np.ndarray:
    if sample_meta.empty:
        return np.asarray([], dtype=int)
    date_set = {str(date) for date in dates}
    sample_dates = sample_meta["date"].dt.strftime("%Y-%m-%d")
    return np.flatnonzero(sample_dates.isin(date_set).to_numpy())


if torch is not None:  # pragma: no cover - depends on torch being available

    class SequenceTransformer(nn.Module):
        def __init__(
            self,
            *,
            feature_dim: int,
            lookback: int,
            hidden_dim: int,
            num_layers: int,
            num_heads: int,
            dropout: float,
            output_dim: int = 1,
        ) -> None:
            super().__init__()
            if hidden_dim % num_heads != 0:
                raise ValueError("hidden_dim must be divisible by num_heads.")
            self.feature_dim = int(feature_dim)
            self.lookback = int(lookback)
            self.hidden_dim = int(hidden_dim)
            self.input_projection = nn.Linear(feature_dim, hidden_dim)
            self.input_norm = nn.LayerNorm(hidden_dim)
            self.positional_embedding = nn.Parameter(torch.zeros(1, lookback, hidden_dim))
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=num_heads,
                dim_feedforward=hidden_dim * 4,
                dropout=dropout,
                batch_first=True,
                activation="gelu",
                norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.head = nn.Sequential(
                nn.LayerNorm(hidden_dim * 2),
                nn.Linear(hidden_dim * 2, hidden_dim),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, output_dim),
            )
            self.dropout = nn.Dropout(dropout)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            hidden = self.input_projection(x)
            hidden = self.input_norm(hidden)
            if hidden.size(1) != self.positional_embedding.size(1):
                raise ValueError(
                    f"Expected sequence length {self.positional_embedding.size(1)} but received {hidden.size(1)}."
                )
            hidden = hidden + self.positional_embedding
            encoded = self.encoder(self.dropout(hidden))
            last_token = encoded[:, -1, :]
            mean_token = encoded.mean(dim=1)
            pooled = torch.cat([last_token, mean_token], dim=-1)
            return self.head(pooled).squeeze(-1)


else:  # pragma: no cover - executed only when torch is absent

    class SequenceTransformer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise ModuleNotFoundError("PyTorch is not installed.")


def build_model(
    *,
    feature_dim: int,
    lookback: int,
    hidden_dim: int,
    num_layers: int,
    num_heads: int,
    dropout: float,
    mode: str,
):
    require_torch()
    output_dim = 1
    return SequenceTransformer(
        feature_dim=feature_dim,
        lookback=lookback,
        hidden_dim=hidden_dim,
        num_layers=num_layers,
        num_heads=num_heads,
        dropout=dropout,
        output_dim=output_dim,
    )


def make_dataloader(
    sequences: np.ndarray,
    targets: np.ndarray,
    *,
    batch_size: int,
    shuffle: bool,
):
    require_torch()
    tensor_x = torch.as_tensor(sequences, dtype=torch.float32)
    tensor_y = torch.as_tensor(targets, dtype=torch.float32)
    dataset = TensorDataset(tensor_x, tensor_y)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle, drop_last=False)


def _resolve_device(device_name: str) -> "torch.device":
    require_torch()
    if device_name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(device_name)


def train_model(
    *,
    train_sequences: np.ndarray,
    train_targets: np.ndarray,
    valid_sequences: np.ndarray,
    valid_targets: np.ndarray,
    feature_dim: int,
    lookback: int,
    hidden_dim: int,
    num_layers: int,
    num_heads: int,
    dropout: float,
    learning_rate: float,
    weight_decay: float,
    batch_size: int,
    max_epochs: int,
    patience: int,
    mode: str,
    device_name: str = "auto",
):
    torch_module = require_torch()
    device = _resolve_device(device_name)

    model = build_model(
        feature_dim=feature_dim,
        lookback=lookback,
        hidden_dim=hidden_dim,
        num_layers=num_layers,
        num_heads=num_heads,
        dropout=dropout,
        mode=mode,
    ).to(device)

    if mode == "classification":
        criterion = torch_module.nn.BCEWithLogitsLoss()
    else:
        criterion = torch_module.nn.MSELoss()

    optimizer = torch_module.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)

    train_loader = make_dataloader(train_sequences, train_targets, batch_size=batch_size, shuffle=True)
    valid_loader = make_dataloader(valid_sequences, valid_targets, batch_size=batch_size, shuffle=False)

    best_state = None
    best_val_loss = float("inf")
    best_epoch = 0
    epochs_without_improvement = 0
    final_train_loss = float("inf")
    final_valid_loss = float("inf")
    start = time.perf_counter()

    for epoch in range(1, max_epochs + 1):
        model.train()
        running_loss = 0.0
        sample_count = 0
        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            batch_size_actual = int(batch_x.size(0))
            running_loss += float(loss.item()) * batch_size_actual
            sample_count += batch_size_actual

        final_train_loss = running_loss / max(sample_count, 1)

        model.eval()
        valid_running_loss = 0.0
        valid_count = 0
        with torch_module.no_grad():
            for batch_x, batch_y in valid_loader:
                batch_x = batch_x.to(device)
                batch_y = batch_y.to(device)
                logits = model(batch_x)
                loss = criterion(logits, batch_y)
                batch_size_actual = int(batch_x.size(0))
                valid_running_loss += float(loss.item()) * batch_size_actual
                valid_count += batch_size_actual
        final_valid_loss = valid_running_loss / max(valid_count, 1)

        if final_valid_loss + 1e-12 < best_val_loss:
            best_val_loss = final_valid_loss
            best_epoch = epoch
            epochs_without_improvement = 0
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    runtime = time.perf_counter() - start
    train_summary = {
        "best_epoch": int(best_epoch),
        "best_val_loss": float(best_val_loss),
        "final_train_loss": float(final_train_loss),
        "final_valid_loss": float(final_valid_loss),
        "device": str(device),
        "runtime_seconds": float(runtime),
        "epochs_ran": int(best_epoch + epochs_without_improvement),
    }
    return model, train_summary, runtime


def predict_model(
    model,
    sequences: np.ndarray,
    *,
    batch_size: int = 256,
    device_name: str = "auto",
) -> np.ndarray:
    torch_module = require_torch()
    if len(sequences) == 0:
        return np.asarray([], dtype=np.float32)
    device = _resolve_device(device_name)
    model = model.to(device)
    model.eval()

    loader = DataLoader(
        TensorDataset(torch_module.as_tensor(sequences, dtype=torch.float32)),
        batch_size=batch_size,
        shuffle=False,
        drop_last=False,
    )
    outputs: list[np.ndarray] = []
    with torch_module.no_grad():
        for (batch_x,) in loader:
            batch_x = batch_x.to(device)
            batch_scores = model(batch_x).detach().cpu().numpy().reshape(-1)
            outputs.append(batch_scores)
    return np.concatenate(outputs, axis=0).astype(np.float32)


def save_feature_importance(model, feature_columns: Sequence[str], output_dir: str | Path) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    if not hasattr(model, "input_projection"):
        importance_df = pd.DataFrame({"feature": list(feature_columns), "importance": 0.0})
    else:
        weights = model.input_projection.weight.detach().cpu().numpy()
        importance = np.linalg.norm(weights, axis=0)
        importance_df = pd.DataFrame(
            {
                "feature": list(feature_columns),
                "importance_norm": importance,
            }
        ).sort_values("importance_norm", ascending=False, kind="stable")
    path = output_path / "feature_importance.csv"
    importance_df.to_csv(path, index=False, encoding="utf-8")
    return path


def save_model_bundle(
    *,
    model,
    output_dir: str | Path,
    metadata: dict[str, object],
    feature_stats: dict[str, dict[str, float]],
) -> tuple[Path, Path, Path]:
    require_torch()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model_path = output_path / "model.pt"
    metadata_path = output_path / "model_metadata.json"
    feature_stats_path = output_path / "feature_stats.json"

    torch.save(model.state_dict(), model_path)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    feature_stats_path.write_text(
        json.dumps(feature_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return model_path, metadata_path, feature_stats_path


def load_model_bundle(
    *,
    model_path: str | Path,
    metadata_path: str | Path,
    feature_dim: int,
    lookback: int,
):
    torch_module = require_torch()
    model_path = Path(model_path)
    metadata_path = Path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model = build_model(
        feature_dim=feature_dim,
        lookback=lookback,
        hidden_dim=int(metadata["hidden_dim"]),
        num_layers=int(metadata["num_layers"]),
        num_heads=int(metadata["num_heads"]),
        dropout=float(metadata["dropout"]),
        mode=str(metadata["mode"]),
    )
    state_dict = torch_module.load(model_path, map_location="cpu")
    model.load_state_dict(state_dict)
    model.eval()
    return model, metadata
