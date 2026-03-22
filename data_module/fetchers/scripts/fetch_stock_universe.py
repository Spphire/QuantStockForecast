#!/usr/bin/env python3
"""Fetch and merge a stock universe into one normalized dataset."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

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
        "--bootstrap-start",
        default="",
        help="Optional historical bootstrap start date for missing symbols (defaults to --start).",
    )
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
        "--incremental",
        action="store_true",
        help="Use existing universe dataset as baseline and only fetch missing tail data per symbol.",
    )
    parser.add_argument(
        "--write-latest-alias",
        action="store_true",
        help="Write an additional stable latest dataset/manifest alias under universes directory.",
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


def universe_stage_root(provider: str, stage_dir: str) -> Path:
    data_dir = default_data_dir()
    stage_root = Path(stage_dir) if stage_dir else data_dir / "interim" / provider / "universes"
    stage_root.mkdir(parents=True, exist_ok=True)
    return stage_root


def universe_output_paths(
    provider: str, name: str, start: str, end: str, adjust: str, stage_dir: str
) -> tuple[Path, Path]:
    stage_root = universe_stage_root(provider, stage_dir)
    parts = [name, normalize_date(start, compact=True), normalize_date(end, compact=True)]
    if adjust:
        parts.append(adjust)
    stem = "_".join(parts)
    return stage_root / f"{stem}_normalized.csv", stage_root / f"{stem}_manifest.json"


def universe_latest_alias_paths(provider: str, name: str, adjust: str, stage_dir: str) -> tuple[Path, Path]:
    stage_root = universe_stage_root(provider, stage_dir)
    suffix = adjust or "none"
    return (
        stage_root / f"{name}_latest_{suffix}_normalized.csv",
        stage_root / f"{name}_latest_{suffix}_manifest.json",
    )


def _parse_day(value: str) -> date:
    return date.fromisoformat(normalize_date(value))


def _to_day_text(value: date) -> str:
    return value.isoformat()


def _stable_existing_universe_path(*, provider: str, name: str, adjust: str, stage_dir: str) -> Path | None:
    latest_path, _ = universe_latest_alias_paths(provider, name, adjust, stage_dir)
    if latest_path.exists():
        return latest_path

    stage_root = universe_stage_root(provider, stage_dir)
    adjust_marker = f"_{adjust}_normalized.csv" if adjust else "_normalized.csv"
    dated_candidates = sorted(
        [
            path
            for path in stage_root.glob(f"{name}_*_normalized.csv")
            if "_latest_" not in path.name
            and not path.name.endswith("_manifest.json")
            and path.name.endswith(adjust_marker)
        ],
        key=lambda path: path.stat().st_mtime,
    )
    if not dated_candidates:
        return None
    return dated_candidates[-1]


def _safe_load_universe_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if frame.empty:
        return frame
    if "date" not in frame.columns or "symbol" not in frame.columns:
        return pd.DataFrame()
    return _canonicalize_frame(frame)


def _canonicalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    if working.empty:
        return working
    working["symbol"] = working["symbol"].astype(str).str.strip().str.upper()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date", "symbol"]).copy()
    working = (
        working.sort_values(["symbol", "date"], kind="stable")
        .drop_duplicates(subset=["symbol", "date"], keep="last")
        .reset_index(drop=True)
    )
    working["date"] = working["date"].dt.strftime("%Y-%m-%d")
    return _order_columns(working)


def _order_columns(frame: pd.DataFrame) -> pd.DataFrame:
    preferred = ["date", "symbol", "open", "high", "low", "close", "volume", "amount", "provider", "adjust"]
    ordered = [column for column in preferred if column in frame.columns]
    remaining = [column for column in frame.columns if column not in ordered]
    return frame[ordered + remaining]


def _combine_frames(existing_frame: pd.DataFrame, incoming_frame: pd.DataFrame) -> pd.DataFrame:
    if existing_frame.empty and incoming_frame.empty:
        return pd.DataFrame()
    if existing_frame.empty:
        return _canonicalize_frame(incoming_frame)
    if incoming_frame.empty:
        return _canonicalize_frame(existing_frame)
    merged = pd.concat([existing_frame, incoming_frame], ignore_index=True)
    return _canonicalize_frame(merged)


def _is_no_new_data_error(provider: str, error: Exception) -> bool:
    text = str(error).lower()
    if provider == "alpaca":
        return "no alpaca bars returned" in text
    if provider == "stooq":
        return "no stooq history returned" in text or "no stooq rows remain" in text
    return False


def _build_member_manifest(
    *,
    provider_label: str,
    symbol: str,
    start: str,
    end: str,
    adjust: str,
    raw_path: Path | None,
    normalized_path: Path | None,
    frame: pd.DataFrame,
    mode: str,
    reused_existing: bool,
    fetched_rows: int,
    previous_date_max: str,
    fetch_error: str = "",
) -> dict[str, Any]:
    payload = {
        "provider": provider_label,
        "symbol": symbol,
        "start": normalize_date(start),
        "end": normalize_date(end),
        "adjust": adjust or "none",
        "raw_path": str(raw_path) if raw_path is not None else "",
        "normalized_path": str(normalized_path) if normalized_path is not None else "",
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "date_min": frame["date"].min() if not frame.empty and "date" in frame.columns else None,
        "date_max": frame["date"].max() if not frame.empty and "date" in frame.columns else None,
        "mode": mode,
        "reused_existing": bool(reused_existing),
        "fetched_rows": int(fetched_rows),
        "previous_date_max": previous_date_max or None,
    }
    if fetch_error:
        payload["fetch_error"] = fetch_error
    return payload


def main() -> int:
    args = parse_args()
    symbols = load_symbols(args.symbols, args.symbols_file)
    if not symbols:
        print("[ERROR] No symbols provided. Use --symbols or --symbols-file.")
        return 1
    start_day = _parse_day(args.start)
    end_day = _parse_day(args.end)
    if start_day > end_day:
        print("[ERROR] --start cannot be later than --end.")
        return 1

    bootstrap_day = _parse_day(args.bootstrap_start) if args.bootstrap_start else start_day

    merged_frames: list[pd.DataFrame] = []
    individual_manifests: list[dict[str, Any]] = []
    failed_symbols: list[dict[str, Any]] = []

    existing_universe_source: str | None = None
    existing_universe_frame = pd.DataFrame()
    if args.incremental:
        existing_path = _stable_existing_universe_path(
            provider=args.provider,
            name=args.name,
            adjust=args.adjust,
            stage_dir=args.stage_dir,
        )
        if existing_path is not None:
            existing_universe_source = str(existing_path)
            try:
                existing_universe_frame = _safe_load_universe_frame(existing_path)
                print(f"[INFO] Incremental baseline: {existing_path}")
            except Exception as exc:
                print(f"[WARN] Failed to load incremental baseline {existing_path}: {exc}")
                existing_universe_frame = pd.DataFrame()

    existing_by_symbol: dict[str, pd.DataFrame] = {}
    if not existing_universe_frame.empty:
        for symbol, frame in existing_universe_frame.groupby("symbol", sort=False):
            existing_by_symbol[str(symbol).upper()] = frame.copy().reset_index(drop=True)

    for index, symbol in enumerate(symbols, start=1):
        symbol_upper = str(symbol).strip().upper()
        print(f"[INFO] Fetching {symbol_upper} ({index}/{len(symbols)})")

        existing_symbol_frame = existing_by_symbol.get(symbol_upper, pd.DataFrame())
        previous_date_max = ""
        fetch_start_day = start_day
        reused_existing = False
        mode = "full"
        if args.incremental and not existing_symbol_frame.empty:
            existing_symbol_frame = _canonicalize_frame(existing_symbol_frame)
            previous_date_max = str(existing_symbol_frame["date"].max())
            last_day = _parse_day(previous_date_max)
            fetch_start_day = max(start_day, last_day + timedelta(days=1))
            mode = "incremental"
        elif args.incremental:
            fetch_start_day = bootstrap_day
            mode = "incremental_bootstrap"

        fetch_start_text = _to_day_text(fetch_start_day)
        fetch_end_text = _to_day_text(end_day)
        raw_path, normalized_path, manifest_path = default_output_paths(
            args.provider,
            symbol_upper,
            fetch_start_text,
            fetch_end_text,
            args.adjust,
            args.raw_dir,
            args.stage_dir,
        )

        raw_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.parent.mkdir(parents=True, exist_ok=True)

        if fetch_start_day > end_day:
            reused_existing = True
            final_symbol_frame = existing_symbol_frame.copy()
            member_manifest = _build_member_manifest(
                provider_label=str(
                    final_symbol_frame["provider"].iloc[-1] if (not final_symbol_frame.empty and "provider" in final_symbol_frame.columns) else args.provider
                ),
                symbol=symbol_upper,
                start=fetch_start_text,
                end=fetch_end_text,
                adjust=args.adjust,
                raw_path=None,
                normalized_path=None,
                frame=final_symbol_frame,
                mode="up_to_date",
                reused_existing=True,
                fetched_rows=0,
                previous_date_max=previous_date_max,
            )
            manifest_path.write_text(
                json.dumps(member_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            merged_frames.append(final_symbol_frame)
            individual_manifests.append(member_manifest)
            continue

        try:
            raw_df, provider_label = fetch_single_symbol(
                args.provider,
                symbol_upper,
                fetch_start_text,
                fetch_end_text,
                args.adjust,
                args.seed + index - 1,
                args.alpaca_env_prefix,
                args.alpaca_feed,
            )
            normalized_df = normalize_dataframe(
                raw_df, provider=provider_label, adjust=args.adjust or "none"
            )
        except Exception as exc:
            if args.incremental and not existing_symbol_frame.empty and _is_no_new_data_error(args.provider, exc):
                reused_existing = True
                final_symbol_frame = existing_symbol_frame.copy()
                member_manifest = _build_member_manifest(
                    provider_label=str(
                        final_symbol_frame["provider"].iloc[-1] if (not final_symbol_frame.empty and "provider" in final_symbol_frame.columns) else args.provider
                    ),
                    symbol=symbol_upper,
                    start=fetch_start_text,
                    end=fetch_end_text,
                    adjust=args.adjust,
                    raw_path=None,
                    normalized_path=None,
                    frame=final_symbol_frame,
                    mode="no_new_data",
                    reused_existing=True,
                    fetched_rows=0,
                    previous_date_max=previous_date_max,
                )
                manifest_path.write_text(
                    json.dumps(member_manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                merged_frames.append(final_symbol_frame)
                individual_manifests.append(member_manifest)
                continue

            if args.incremental and not existing_symbol_frame.empty:
                print(f"[WARN] Incremental fetch failed for {symbol_upper}, fallback to existing data: {exc}")
                failed_symbols.append(
                    {
                        "symbol": symbol_upper,
                        "error": str(exc),
                        "reused_existing": True,
                        "previous_date_max": previous_date_max or None,
                    }
                )
                reused_existing = True
                final_symbol_frame = existing_symbol_frame.copy()
                member_manifest = _build_member_manifest(
                    provider_label=str(
                        final_symbol_frame["provider"].iloc[-1] if (not final_symbol_frame.empty and "provider" in final_symbol_frame.columns) else args.provider
                    ),
                    symbol=symbol_upper,
                    start=fetch_start_text,
                    end=fetch_end_text,
                    adjust=args.adjust,
                    raw_path=None,
                    normalized_path=None,
                    frame=final_symbol_frame,
                    mode="incremental_fallback",
                    reused_existing=True,
                    fetched_rows=0,
                    previous_date_max=previous_date_max,
                    fetch_error=str(exc),
                )
                manifest_path.write_text(
                    json.dumps(member_manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                merged_frames.append(final_symbol_frame)
                individual_manifests.append(member_manifest)
                continue

            print(f"[WARN] Failed to fetch {symbol_upper}: {exc}")
            failed_symbols.append({"symbol": symbol_upper, "error": str(exc)})
            if not args.continue_on_error:
                return 1
            continue

        raw_df.to_csv(raw_path, index=False, encoding="utf-8-sig")
        normalized_df.to_csv(normalized_path, index=False, encoding="utf-8")

        fetched_manifest = build_manifest(
            provider_label,
            symbol_upper,
            fetch_start_text,
            fetch_end_text,
            args.adjust,
            raw_path,
            normalized_path,
            normalized_df,
        )
        final_symbol_frame = _combine_frames(existing_symbol_frame, normalized_df)
        member_manifest = _build_member_manifest(
            provider_label=provider_label,
            symbol=symbol_upper,
            start=fetch_start_text,
            end=fetch_end_text,
            adjust=args.adjust,
            raw_path=raw_path,
            normalized_path=normalized_path,
            frame=final_symbol_frame,
            mode=mode,
            reused_existing=reused_existing,
            fetched_rows=int(len(normalized_df)),
            previous_date_max=previous_date_max,
        )
        member_manifest["fetched_window"] = fetched_manifest
        manifest_path.write_text(
            json.dumps(member_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        merged_frames.append(final_symbol_frame)
        individual_manifests.append(member_manifest)

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
        "provider_sources": sorted({str(item.get("provider", "")) for item in individual_manifests if str(item.get("provider", ""))}),
        "name": args.name,
        "mode": "incremental" if args.incremental else "full",
        "symbol_count_requested": len(symbols),
        "symbol_count_success": int(merged_df["symbol"].nunique()),
        "symbols": sorted(merged_df["symbol"].unique().tolist()),
        "start": normalize_date(args.start),
        "end": normalize_date(args.end),
        "adjust": args.adjust or "none",
        "rows": int(len(merged_df)),
        "columns": list(merged_df.columns),
        "merged_path": str(merged_path),
        "existing_dataset_path": existing_universe_source,
        "failed_symbols": failed_symbols,
        "members": individual_manifests,
    }
    merged_manifest_path.write_text(
        json.dumps(merged_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.incremental or args.write_latest_alias:
        latest_path, latest_manifest_path = universe_latest_alias_paths(
            args.provider,
            args.name,
            args.adjust,
            args.stage_dir,
        )
        merged_df.to_csv(latest_path, index=False, encoding="utf-8")
        latest_manifest = dict(merged_manifest)
        latest_manifest["merged_path"] = str(latest_path)
        latest_manifest["is_latest_alias"] = True
        latest_manifest_path.write_text(
            json.dumps(latest_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[OK] Universe latest dataset: {latest_path}")
        print(f"[OK] Universe latest manifest: {latest_manifest_path}")

    print(f"[OK] Universe dataset: {merged_path}")
    print(f"[OK] Universe manifest: {merged_manifest_path}")
    print(f"[INFO] Successful symbols: {merged_manifest['symbol_count_success']}/{len(symbols)}")
    print(f"[INFO] Rows: {len(merged_df)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
