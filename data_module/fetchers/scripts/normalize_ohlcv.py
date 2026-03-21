#!/usr/bin/env python3
"""Normalize stock CSV headers into the project's shared schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from data_module.common.stock_schema import canonical_columns, normalize_dataframe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize CSV headers into the project's OHLCV schema."
    )
    parser.add_argument("input_csv", help="Source CSV file.")
    parser.add_argument("output_csv", help="Destination CSV file.")
    parser.add_argument(
        "--provider",
        default="csv-import",
        help="Provider label written to the normalized output.",
    )
    parser.add_argument(
        "--adjust",
        default="",
        help="Adjustment label written to the normalized output, if applicable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_csv)
    output_path = Path(args.output_csv)

    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}")
        return 1

    try:
        raw_df = pd.read_csv(input_path, encoding="utf-8-sig")
        normalized_df = normalize_dataframe(
            raw_df, provider=args.provider, adjust=args.adjust or None
        )
    except Exception as exc:
        print(f"[ERROR] Failed to normalize file: {exc}")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_df.to_csv(output_path, index=False, encoding="utf-8")

    print(f"[OK] Wrote normalized file to: {output_path}")
    print(f"[INFO] Columns: {', '.join(canonical_columns(normalized_df.columns))}")
    print(f"[INFO] Rows: {len(normalized_df)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
