"""Shared stock dataset schema used by fetchers and model scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PRICE_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
CORE_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume"]
OPTIONAL_COLUMNS = [
    "amount",
    "turnover",
    "pct_change",
    "price_change",
    "amplitude",
    "provider",
    "adjust",
]

NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "turnover",
    "pct_change",
    "price_change",
    "amplitude",
]

ALIASES = {
    "date": {"date", "trade_date", "datetime", "day", "日期", "时间"},
    "symbol": {"symbol", "code", "ticker", "ts_code", "股票代码"},
    "open": {"open", "open_price", "开盘"},
    "high": {"high", "high_price", "最高"},
    "low": {"low", "low_price", "最低"},
    "close": {"close", "close_price", "price", "收盘"},
    "volume": {"volume", "vol", "trade_volume", "成交量"},
    "amount": {"amount", "turnover_amount", "trade_amount", "成交额"},
    "turnover": {"turnover", "换手率"},
    "pct_change": {"pct_change", "涨跌幅"},
    "price_change": {"price_change", "涨跌额"},
    "amplitude": {"amplitude", "振幅"},
    "provider": {"provider"},
    "adjust": {"adjust"},
}


def normalize_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def canonical_columns(columns: Iterable[str]) -> list[str]:
    ordered = CORE_COLUMNS + OPTIONAL_COLUMNS
    existing = set(columns)
    return [column for column in ordered if column in existing]


def missing_required_columns(columns: Iterable[str]) -> list[str]:
    existing = set(columns)
    return [column for column in REQUIRED_PRICE_COLUMNS if column not in existing]


def build_column_mapping(columns: Iterable[str]) -> dict[str, str]:
    normalized_to_original = {normalize_header(column): column for column in columns}
    mapping: dict[str, str] = {}

    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            alias_key = normalize_header(alias)
            if alias_key in normalized_to_original:
                mapping[canonical] = normalized_to_original[alias_key]
                break

    return mapping


def normalize_dataframe(
    df: pd.DataFrame, *, provider: str | None = None, adjust: str | None = None
) -> pd.DataFrame:
    mapping = build_column_mapping(df.columns)
    missing = missing_required_columns(mapping.keys())
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    renamed = df.rename(columns={source: target for target, source in mapping.items()}).copy()
    selected = canonical_columns(renamed.columns)
    normalized = renamed[selected].copy()

    for column in NUMERIC_COLUMNS:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")

    if "symbol" in normalized.columns:
        normalized["symbol"] = normalized["symbol"].astype(str).str.strip()
    else:
        normalized["symbol"] = ""

    if provider is not None:
        normalized["provider"] = provider

    if adjust is not None:
        normalized["adjust"] = adjust

    normalized = normalized.dropna(subset=["date"])
    normalized = normalized.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
    normalized["date"] = normalized["date"].dt.strftime("%Y-%m-%d")

    return normalized[canonical_columns(normalized.columns)]


def default_data_dir() -> Path:
    return PROJECT_ROOT / "data"
