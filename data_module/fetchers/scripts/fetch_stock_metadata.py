#!/usr/bin/env python3
"""Fetch stock industry metadata for a symbol list."""

from __future__ import annotations

import argparse
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch stock industry metadata for a symbol list and save it as a CSV."
    )
    parser.add_argument(
        "--provider",
        default="akshare",
        choices=["akshare", "wikipedia_sp500"],
        help="Metadata source provider.",
    )
    parser.add_argument(
        "--symbols",
        default="",
        help="Comma-separated stock symbols. Use either this or --symbols-file.",
    )
    parser.add_argument(
        "--symbols-file",
        default="",
        help="Text file containing one stock symbol per line.",
    )
    parser.add_argument(
        "--output-csv",
        required=True,
        help="Destination CSV path for metadata.",
    )
    parser.add_argument(
        "--industry-standard",
        default="申银万国行业分类标准",
        help="Preferred industry classification standard.",
    )
    parser.add_argument(
        "--start-date",
        default="20091227",
        help="Start date used for CNINFO industry history lookup.",
    )
    parser.add_argument(
        "--end-date",
        default="20301231",
        help="End date used for CNINFO industry history lookup.",
    )
    return parser.parse_args()


def load_symbols(symbols_arg: str, symbols_file: str) -> list[str]:
    symbols: list[str] = []
    if symbols_arg:
        symbols.extend(part.strip() for part in symbols_arg.split(","))
    if symbols_file:
        file_path = Path(symbols_file)
        symbols.extend(
            line.strip()
            for line in file_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    deduped: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if symbol and symbol not in seen:
            deduped.append(symbol)
            seen.add(symbol)
    return deduped


def pick_latest_industry_row(df: pd.DataFrame, preferred_standard: str) -> pd.Series:
    working = df.copy()
    working["变更日期"] = pd.to_datetime(working["变更日期"], errors="coerce")
    preferred = working[working["分类标准"] == preferred_standard].copy()
    candidate = preferred if not preferred.empty else working
    candidate = candidate.sort_values("变更日期", ascending=False, kind="stable")
    return candidate.iloc[0]


def fetch_one(
    symbol: str, preferred_standard: str, start_date: str, end_date: str
) -> dict[str, object]:
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("akshare is required to fetch stock metadata.") from exc

    raw = ak.stock_industry_change_cninfo(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )
    if raw.empty:
        raise ValueError("No industry history rows returned.")

    row = pick_latest_industry_row(raw, preferred_standard)
    return {
        "symbol": str(row.get("证券代码", symbol)).zfill(6),
        "name": row.get("新证券简称", ""),
        "industry_standard": row.get("分类标准", ""),
        "industry_code": row.get("行业编码", ""),
        "industry_sector": row.get("行业门类", ""),
        "industry_group": row.get("行业大类", ""),
        "industry_subgroup": row.get("行业中类", ""),
        "industry_detail": row.get("行业次类", ""),
        "industry_change_date": str(row.get("变更日期", ""))[:10],
    }


def fetch_wikipedia_sp500_metadata(symbols: list[str]) -> pd.DataFrame:
    headers = {"User-Agent": "Mozilla/5.0"}
    html = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers=headers,
        timeout=30,
    ).text
    table = pd.read_html(StringIO(html))[0]
    working = table.rename(
        columns={
            "Symbol": "symbol",
            "Security": "name",
            "GICS Sector": "industry_group",
            "GICS Sub-Industry": "industry_subgroup",
        }
    ).copy()
    working["symbol"] = working["symbol"].astype(str).str.replace(".", "-", regex=False).str.upper()
    working = working[working["symbol"].isin([str(symbol).strip().upper() for symbol in symbols])].copy()
    if working.empty:
        raise ValueError("No requested symbols were found in the Wikipedia S&P 500 table.")

    working["industry_standard"] = "GICS (Wikipedia S&P 500)"
    working["industry_code"] = ""
    working["industry_sector"] = working["industry_group"]
    working["industry_detail"] = working["industry_subgroup"]
    working["industry_change_date"] = pd.Timestamp.today().strftime("%Y-%m-%d")
    return working[
        [
            "symbol",
            "name",
            "industry_standard",
            "industry_code",
            "industry_sector",
            "industry_group",
            "industry_subgroup",
            "industry_detail",
            "industry_change_date",
        ]
    ].drop_duplicates(subset=["symbol"], keep="first")


def main() -> int:
    args = parse_args()
    symbols = load_symbols(args.symbols, args.symbols_file)
    if not symbols:
        print("[ERROR] No symbols provided. Use --symbols or --symbols-file.")
        return 1

    records: list[dict[str, object]] = []
    if args.provider == "wikipedia_sp500":
        try:
            df = fetch_wikipedia_sp500_metadata(symbols)
        except Exception as exc:
            print(f"[ERROR] Failed to fetch metadata from Wikipedia: {exc}")
            return 1
    else:
        for index, symbol in enumerate(symbols, start=1):
            print(f"[INFO] Fetching metadata for {symbol} ({index}/{len(symbols)})")
            try:
                records.append(
                    fetch_one(
                        symbol,
                        args.industry_standard,
                        args.start_date,
                        args.end_date,
                    )
                )
            except Exception as exc:
                print(f"[WARN] Failed to fetch metadata for {symbol}: {exc}")

        if not records:
            print("[ERROR] No metadata records were fetched successfully.")
            return 1

        df = pd.DataFrame(records).drop_duplicates(subset=["symbol"], keep="first")
    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")

    print(f"[OK] Metadata CSV: {output_path}")
    print(f"[INFO] Rows: {len(df)}")
    print(f"[INFO] Industry groups: {df['industry_group'].nunique(dropna=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
