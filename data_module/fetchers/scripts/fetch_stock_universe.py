#!/usr/bin/env python3
"""Fetch and merge a stock universe into one normalized dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from data_module.common.stock_schema import default_data_dir, normalize_dataframe
from data_module.fetchers.scripts.fetch_stock_history import (
    build_manifest,
    default_output_paths,
    fetch_akshare_history,
    fetch_alpaca_history,
    fetch_demo_history,
    fetch_stooq_history,
    normalize_date,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch multiple stock symbols and merge them into one normalized universe dataset."
    )
    parser.add_argument(
        "--provider",
        default="akshare",
        choices=["demo", "akshare", "stooq", "alpaca"],
        help="Data provider used for all requested symbols.",
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
        "--name",
        default="custom_universe",
        help="Logical universe name used in merged output filenames.",
    )
    parser.add_argument("--start", required=True, help="Start date in YYYY-MM-DD or YYYYMMDD format.")
    parser.add_argument("--end", required=True, help="End date in YYYY-MM-DD or YYYYMMDD format.")
    parser.add_argument(
        "--adjust",
        default="hfq",
        choices=["", "qfq", "hfq"],
        help="Adjustment mode used by the provider when supported.",
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
        help="Random seed used only for the demo provider.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Skip failed symbols and continue fetching the remaining universe.",
    )
    parser.add_argument(
        "--alpaca-env-prefix",
        default="ALPACA_ZERO_SHOT",
        help="Credential prefix used for Alpaca market data (provider=alpaca).",
    )
    parser.add_argument(
        "--alpaca-feed",
        default="iex",
        choices=["iex", "sip"],
        help="Market data feed used for Alpaca provider.",
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


def fetch_single_symbol(
    provider: str,
    symbol: str,
    start: str,
    end: str,
    adjust: str,
    seed: int,
    alpaca_env_prefix: str,
    alpaca_feed: str,
) -> tuple[pd.DataFrame, str]:
    if provider == "demo":
        return fetch_demo_history(symbol, start, end, seed), "demo"
    if provider == "stooq":
        return fetch_stooq_history(symbol, start, end)
    if provider == "alpaca":
        return fetch_alpaca_history(
            symbol,
            start,
            end,
            env_prefix=alpaca_env_prefix,
            feed=alpaca_feed,
        )
    return fetch_akshare_history(symbol, start, end, adjust)


def universe_output_paths(
    provider: str, name: str, start: str, end: str, adjust: str, stage_dir: str
) -> tuple[Path, Path]:
    data_dir = default_data_dir()
    stage_root = Path(stage_dir) if stage_dir else data_dir / "interim" / provider / "universes"
    stage_root.mkdir(parents=True, exist_ok=True)

    parts = [name, normalize_date(start, compact=True), normalize_date(end, compact=True)]
    if adjust:
        parts.append(adjust)
    stem = "_".join(parts)
    return stage_root / f"{stem}_normalized.csv", stage_root / f"{stem}_manifest.json"


def main() -> int:
    args = parse_args()
    symbols = load_symbols(args.symbols, args.symbols_file)
    if not symbols:
        print("[ERROR] No symbols provided. Use --symbols or --symbols-file.")
        return 1

    merged_frames: list[pd.DataFrame] = []
    individual_manifests: list[dict[str, object]] = []
    failed_symbols: list[dict[str, str]] = []

    for index, symbol in enumerate(symbols, start=1):
        print(f"[INFO] Fetching {symbol} ({index}/{len(symbols)})")
        raw_path, normalized_path, manifest_path = default_output_paths(
            args.provider,
            symbol,
            args.start,
            args.end,
            args.adjust,
            args.raw_dir,
            args.stage_dir,
        )

        raw_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            raw_df, provider_label = fetch_single_symbol(
                args.provider,
                symbol,
                args.start,
                args.end,
                args.adjust,
                args.seed + index - 1,
                args.alpaca_env_prefix,
                args.alpaca_feed,
            )
            normalized_df = normalize_dataframe(
                raw_df, provider=provider_label, adjust=args.adjust or "none"
            )
        except Exception as exc:
            print(f"[WARN] Failed to fetch {symbol}: {exc}")
            failed_symbols.append({"symbol": symbol, "error": str(exc)})
            if not args.continue_on_error:
                return 1
            continue

        raw_df.to_csv(raw_path, index=False, encoding="utf-8-sig")
        normalized_df.to_csv(normalized_path, index=False, encoding="utf-8")

        manifest = build_manifest(
            provider_label,
            symbol,
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

        merged_frames.append(normalized_df)
        individual_manifests.append(manifest)

    if not merged_frames:
        print("[ERROR] No symbol data was fetched successfully.")
        return 1

    merged_df = (
        pd.concat(merged_frames, ignore_index=True)
        .sort_values(["date", "symbol"], kind="stable")
        .reset_index(drop=True)
    )

    merged_path, merged_manifest_path = universe_output_paths(
        args.provider, args.name, args.start, args.end, args.adjust, args.stage_dir
    )
    merged_df.to_csv(merged_path, index=False, encoding="utf-8")

    merged_manifest = {
        "provider": args.provider,
        "provider_sources": sorted({item["provider"] for item in individual_manifests}),
        "name": args.name,
        "symbol_count_requested": len(symbols),
        "symbol_count_success": int(merged_df["symbol"].nunique()),
        "symbols": sorted(merged_df["symbol"].unique().tolist()),
        "start": normalize_date(args.start),
        "end": normalize_date(args.end),
        "adjust": args.adjust or "none",
        "rows": int(len(merged_df)),
        "columns": list(merged_df.columns),
        "merged_path": str(merged_path),
        "failed_symbols": failed_symbols,
        "members": individual_manifests,
    }
    merged_manifest_path.write_text(
        json.dumps(merged_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Universe dataset: {merged_path}")
    print(f"[OK] Universe manifest: {merged_manifest_path}")
    print(f"[INFO] Successful symbols: {merged_manifest['symbol_count_success']}/{len(symbols)}")
    print(f"[INFO] Rows: {len(merged_df)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
