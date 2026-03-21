#!/usr/bin/env python3
"""Validate a CSV dataset before LightGBM modeling."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from data_module.common.stock_schema import normalize_dataframe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate whether a CSV file matches the stock modeling baseline schema."
    )
    parser.add_argument("csv_path", help="Path to the CSV dataset to validate.")
    parser.add_argument(
        "--target",
        default="",
        help="Optional target column to validate, such as target_up_1d or target_return_5d.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.csv_path)

    if not path.exists():
        print(f"[ERROR] File not found: {path}")
        return 1

    if path.suffix.lower() != ".csv":
        print(f"[ERROR] Expected a .csv file: {path}")
        return 1

    try:
        raw_df = pd.read_csv(path, encoding="utf-8-sig")
        normalized_df = normalize_dataframe(raw_df)
    except Exception as exc:
        print(f"[ERROR] Failed to validate dataset: {exc}")
        return 1

    columns = list(normalized_df.columns)
    row_count = len(normalized_df)
    symbol_count = int(normalized_df["symbol"].replace("", pd.NA).dropna().nunique())
    date_min = normalized_df["date"].min() if row_count else None
    date_max = normalized_df["date"].max() if row_count else None

    print(f"[INFO] File: {path}")
    print(f"[INFO] Columns: {', '.join(columns)}")
    print(f"[INFO] Rows: {row_count}")
    print(f"[INFO] Symbols: {symbol_count}")
    print(f"[INFO] Date range: {date_min} -> {date_max}")

    if row_count == 0:
        print("[ERROR] CSV has no data rows.")
        return 1

    if args.target and args.target not in raw_df.columns and args.target not in normalized_df.columns:
        print(f"[ERROR] Missing target column: {args.target}")
        return 1

    duplicate_rows = normalized_df.duplicated(subset=["date", "symbol"], keep=False).sum()
    if duplicate_rows:
        print(f"[WARN] Duplicate date/symbol rows detected: {duplicate_rows}")

    if normalized_df["date"].is_monotonic_increasing:
        print("[INFO] Dates are globally sorted.")

    print("[OK] Dataset matches the baseline stock schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
