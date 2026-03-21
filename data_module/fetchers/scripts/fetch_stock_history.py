#!/usr/bin/env python3
"""Fetch stock history into raw and normalized project datasets."""

from __future__ import annotations

import argparse
import json
import sys
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from data_module.common.stock_schema import default_data_dir, normalize_dataframe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch stock history and normalize it into the shared project schema."
    )
    parser.add_argument(
        "--provider",
        default="demo",
        choices=["demo", "akshare", "stooq"],
        help="Data source provider. Use demo for a dependency-free smoke test.",
    )
    parser.add_argument("--symbol", required=True, help="Stock symbol or code, such as 000001.")
    parser.add_argument(
        "--start",
        required=True,
        help="Start date in YYYY-MM-DD or YYYYMMDD format.",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="End date in YYYY-MM-DD or YYYYMMDD format.",
    )
    parser.add_argument(
        "--adjust",
        default="",
        choices=["", "qfq", "hfq"],
        help="Price adjustment label for provider outputs when supported.",
    )
    parser.add_argument(
        "--raw-dir",
        default="",
        help="Optional override for the raw output directory.",
    )
    parser.add_argument(
        "--stage-dir",
        default="",
        help="Optional override for the normalized output directory.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed used only by the demo provider.",
    )
    return parser.parse_args()


def normalize_date(value: str, *, compact: bool = False) -> str:
    normalized = pd.to_datetime(value).strftime("%Y-%m-%d")
    return normalized.replace("-", "") if compact else normalized


def default_output_paths(
    provider: str, symbol: str, start: str, end: str, adjust: str, raw_dir: str, stage_dir: str
) -> tuple[Path, Path, Path]:
    data_dir = default_data_dir()
    raw_root = Path(raw_dir) if raw_dir else data_dir / "raw" / provider
    stage_root = Path(stage_dir) if stage_dir else data_dir / "interim" / provider

    suffix_parts = [symbol, normalize_date(start, compact=True), normalize_date(end, compact=True)]
    if adjust:
        suffix_parts.append(adjust)
    stem = "_".join(suffix_parts)

    raw_path = raw_root / f"{stem}_raw.csv"
    normalized_path = stage_root / f"{stem}_normalized.csv"
    manifest_path = stage_root / f"{stem}_manifest.json"
    return raw_path, normalized_path, manifest_path


def fetch_demo_history(symbol: str, start: str, end: str, seed: int) -> pd.DataFrame:
    dates = pd.date_range(normalize_date(start), normalize_date(end), freq="B")
    if len(dates) < 30:
        raise ValueError("Demo provider needs at least 30 business days to produce a useful dataset.")

    rng = np.random.default_rng(seed)
    daily_returns = rng.normal(loc=0.0008, scale=0.018, size=len(dates))
    close = 20 * np.cumprod(1 + daily_returns)
    open_price = close * (1 + rng.normal(0.0, 0.004, size=len(dates)))
    high = np.maximum(open_price, close) * (1 + rng.uniform(0.001, 0.02, size=len(dates)))
    low = np.minimum(open_price, close) * (1 - rng.uniform(0.001, 0.02, size=len(dates)))
    volume = rng.integers(100_000, 600_000, size=len(dates))
    amount = volume * close

    return pd.DataFrame(
        {
            "trade_date": dates.strftime("%Y-%m-%d"),
            "code": symbol,
            "open_price": np.round(open_price, 4),
            "high_price": np.round(high, 4),
            "low_price": np.round(low, 4),
            "close_price": np.round(close, 4),
            "vol": volume,
            "amount": np.round(amount, 2),
        }
    )


def with_market_prefix(symbol: str) -> str:
    if symbol.startswith(("sh", "sz", "bj")):
        return symbol
    if symbol.startswith(("6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"


def attach_symbol(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    working = df.copy()
    if "symbol" not in working.columns and "code" not in working.columns and "股票代码" not in working.columns:
        working["symbol"] = symbol
    return working


def fetch_akshare_history(symbol: str, start: str, end: str, adjust: str) -> tuple[pd.DataFrame, str]:
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "akshare is not installed. Install project dependencies before using --provider akshare."
        ) from exc

    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=normalize_date(start, compact=True),
            end_date=normalize_date(end, compact=True),
            adjust=adjust,
        )
        return attach_symbol(df, symbol), "akshare-eastmoney"
    except Exception as primary_exc:
        try:
            df = ak.stock_zh_a_daily(
                symbol=with_market_prefix(symbol),
                start_date=normalize_date(start, compact=True),
                end_date=normalize_date(end, compact=True),
                adjust=adjust,
            )
            return attach_symbol(df, symbol), "akshare-sina"
        except Exception as secondary_exc:
            raise RuntimeError(
                f"Eastmoney fetch failed: {primary_exc}; Sina fetch failed: {secondary_exc}"
            ) from secondary_exc


def stooq_symbol(symbol: str) -> str:
    cleaned = str(symbol).strip().upper()
    if cleaned.endswith(".US"):
        return cleaned.lower()
    return f"{cleaned.lower()}.us"


def fetch_stooq_history(symbol: str, start: str, end: str) -> tuple[pd.DataFrame, str]:
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol(symbol)}&i=d"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    if "No data" in response.text or not response.text.strip():
        raise ValueError(f"No Stooq history returned for {symbol}.")

    raw_df = pd.read_csv(StringIO(response.text))
    if raw_df.empty:
        raise ValueError(f"Empty Stooq history returned for {symbol}.")

    working = raw_df.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    ).copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"]).copy()
    start_ts = pd.to_datetime(normalize_date(start))
    end_ts = pd.to_datetime(normalize_date(end))
    working = working[(working["date"] >= start_ts) & (working["date"] <= end_ts)].copy()
    if working.empty:
        raise ValueError(f"No Stooq rows remain for {symbol} after date filtering.")

    working["symbol"] = str(symbol).strip().upper()
    working["amount"] = pd.to_numeric(working["close"], errors="coerce") * pd.to_numeric(
        working["volume"], errors="coerce"
    )
    return working, "stooq-us"


def build_manifest(
    provider: str,
    symbol: str,
    start: str,
    end: str,
    adjust: str,
    raw_path: Path,
    normalized_path: Path,
    normalized_df: pd.DataFrame,
) -> dict[str, object]:
    return {
        "provider": provider,
        "symbol": symbol,
        "start": normalize_date(start),
        "end": normalize_date(end),
        "adjust": adjust or "none",
        "raw_path": str(raw_path),
        "normalized_path": str(normalized_path),
        "rows": int(len(normalized_df)),
        "columns": list(normalized_df.columns),
        "date_min": normalized_df["date"].min() if not normalized_df.empty else None,
        "date_max": normalized_df["date"].max() if not normalized_df.empty else None,
    }


def main() -> int:
    args = parse_args()
    raw_path, normalized_path, manifest_path = default_output_paths(
        args.provider,
        args.symbol,
        args.start,
        args.end,
        args.adjust,
        args.raw_dir,
        args.stage_dir,
    )

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if args.provider == "demo":
            raw_df = attach_symbol(
                fetch_demo_history(args.symbol, args.start, args.end, args.seed), args.symbol
            )
            provider_label = "demo"
        elif args.provider == "stooq":
            raw_df, provider_label = fetch_stooq_history(args.symbol, args.start, args.end)
        else:
            raw_df, provider_label = fetch_akshare_history(
                args.symbol, args.start, args.end, args.adjust
            )
    except Exception as exc:
        print(f"[ERROR] Failed to fetch data: {exc}")
        return 1

    raw_df.to_csv(raw_path, index=False, encoding="utf-8-sig")

    try:
        normalized_df = normalize_dataframe(
            raw_df, provider=provider_label, adjust=args.adjust or "none"
        )
    except Exception as exc:
        print(f"[ERROR] Failed to normalize provider output: {exc}")
        return 1

    normalized_df.to_csv(normalized_path, index=False, encoding="utf-8")
    manifest = build_manifest(
        provider_label,
        args.symbol,
        args.start,
        args.end,
        args.adjust,
        raw_path,
        normalized_path,
        normalized_df,
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Raw file: {raw_path}")
    print(f"[OK] Normalized file: {normalized_path}")
    print(f"[OK] Manifest: {manifest_path}")
    print(f"[INFO] Rows: {len(normalized_df)}")
    print(f"[INFO] Columns: {', '.join(normalized_df.columns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
