#!/usr/bin/env python3
"""Run a simple top-k cross-sectional backtest on model predictions."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest top-k stock selection from LightGBM prediction outputs."
    )
    parser.add_argument("predictions_csv", help="Prediction CSV emitted by train_lightgbm.py.")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory used to write backtest outputs. Defaults next to the predictions file.",
    )
    parser.add_argument(
        "--score-column",
        default="",
        help="Prediction score column. Defaults to pred_probability or pred_return.",
    )
    parser.add_argument(
        "--return-column",
        default="",
        help="Forward return column. Defaults to the first column named target_return_*.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of symbols selected on each rebalance date.",
    )
    parser.add_argument(
        "--rebalance-step",
        type=int,
        default=0,
        help="Use every Nth trading date as a rebalance point. Defaults to the forecast horizon if it can be inferred.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=float("-inf"),
        help="Minimum score required before a row is eligible for selection.",
    )
    parser.add_argument(
        "--require-positive-label",
        action="store_true",
        help="When pred_label exists, only select rows whose pred_label is 1.",
    )
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=10.0,
        help="One-way transaction cost in basis points applied to portfolio turnover.",
    )
    parser.add_argument(
        "--min-close",
        type=float,
        default=0.0,
        help="Minimum close price filter for candidate stocks.",
    )
    parser.add_argument(
        "--max-close",
        type=float,
        default=0.0,
        help="Maximum close price filter for candidate stocks. Use 0 to disable.",
    )
    parser.add_argument(
        "--min-amount",
        type=float,
        default=0.0,
        help="Minimum成交额 filter when the amount column is available in predictions.",
    )
    parser.add_argument(
        "--metadata-csv",
        default="",
        help="Optional metadata CSV joined by symbol, for example industry or size buckets.",
    )
    parser.add_argument(
        "--group-column",
        default="",
        help="Primary metadata column used to cap exposure, such as industry.",
    )
    parser.add_argument(
        "--max-per-group",
        type=int,
        default=0,
        help="Maximum selected names per primary group. Use 0 to disable.",
    )
    parser.add_argument(
        "--secondary-group-column",
        default="",
        help="Optional second metadata column, such as size_bucket.",
    )
    parser.add_argument(
        "--secondary-max-per-group",
        type=int,
        default=0,
        help="Maximum selected names per secondary group. Use 0 to disable.",
    )
    return parser.parse_args()


def infer_horizon_from_return_column(return_column: str) -> int:
    match = re.search(r"target_return_(\d+)d", return_column)
    return int(match.group(1)) if match else 1


def detect_score_column(df: pd.DataFrame, requested: str) -> str:
    if requested:
        return requested
    for candidate in ["pred_probability", "pred_return"]:
        if candidate in df.columns:
            return candidate
    raise ValueError("Could not infer score column. Pass --score-column explicitly.")


def detect_return_column(df: pd.DataFrame, requested: str) -> str:
    if requested:
        return requested
    for column in df.columns:
        if column.startswith("target_return_"):
            return column
    raise ValueError("Could not infer forward return column. Pass --return-column explicitly.")


def max_drawdown(equity_curve: pd.Series) -> float:
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1.0
    return float(drawdown.min())


def portfolio_turnover(previous_symbols: list[str], current_symbols: list[str]) -> float:
    previous_set = set(previous_symbols)
    current_set = set(current_symbols)
    if not current_set and not previous_set:
        return 0.0
    if not previous_set:
        return 1.0 if current_set else 0.0
    if not current_set:
        return 1.0
    overlap = len(previous_set & current_set)
    return 1.0 - overlap / max(len(previous_set), len(current_set))


def annualized_return(total_return: float, periods: int, rebalances_per_year: float) -> float | None:
    if periods <= 0 or total_return <= -1 or rebalances_per_year <= 0:
        return None
    years = periods / rebalances_per_year
    if years <= 0:
        return None
    return float((1 + total_return) ** (1 / years) - 1)


def merge_metadata(df: pd.DataFrame, metadata_csv: str) -> pd.DataFrame:
    metadata_path = Path(metadata_csv)
    metadata_df = pd.read_csv(metadata_path, encoding="utf-8-sig")
    metadata_df["symbol"] = metadata_df["symbol"].astype(str).str.zfill(6)
    merged = df.copy()
    merged["symbol"] = merged["symbol"].astype(str).str.zfill(6)
    return merged.merge(metadata_df, on="symbol", how="left", suffixes=("", "_meta"))


def assign_quantile_bucket(series: pd.Series, labels: list[str]) -> pd.Series:
    valid = pd.to_numeric(series, errors="coerce")
    result = pd.Series(["unknown"] * len(valid), index=valid.index, dtype="object")
    non_null = valid.dropna()
    if non_null.empty:
        return result
    rank_pct = non_null.rank(method="average", pct=True)
    bucket_codes = np.minimum((rank_pct * len(labels)).astype(int), len(labels) - 1)
    result.loc[non_null.index] = [labels[int(code)] for code in bucket_codes]
    return result


def ensure_group_columns(df: pd.DataFrame, requested_columns: list[str]) -> pd.DataFrame:
    working = df.copy()
    for column in requested_columns:
        if not column or column in working.columns:
            continue
        if column == "amount_bucket" and "amount" in working.columns:
            working[column] = working.groupby("date")["amount"].transform(
                lambda series: assign_quantile_bucket(
                    series, ["liq_low", "liq_mid_low", "liq_mid", "liq_mid_high", "liq_high"]
                )
            )
        elif column == "turnover_bucket" and "turnover" in working.columns:
            working[column] = working.groupby("date")["turnover"].transform(
                lambda series: assign_quantile_bucket(
                    series, ["turn_low", "turn_mid_low", "turn_mid", "turn_mid_high", "turn_high"]
                )
            )
        elif column == "price_bucket_dynamic" and "close" in working.columns:
            working[column] = working.groupby("date")["close"].transform(
                lambda series: assign_quantile_bucket(
                    series, ["price_low", "price_mid_low", "price_mid", "price_mid_high", "price_high"]
                )
            )
    return working


def capped_selection(
    eligible: pd.DataFrame,
    score_column: str,
    top_k: int,
    group_column: str,
    max_per_group: int,
    secondary_group_column: str,
    secondary_max_per_group: int,
) -> pd.DataFrame:
    if not group_column and not secondary_group_column:
        return eligible.sort_values(score_column, ascending=False, kind="stable").head(top_k)

    selected_rows: list[int] = []
    primary_counts: dict[object, int] = {}
    secondary_counts: dict[object, int] = {}

    ordered = eligible.sort_values(score_column, ascending=False, kind="stable")
    for idx, row in ordered.iterrows():
        if len(selected_rows) >= top_k:
            break

        primary_ok = True
        if group_column and max_per_group > 0:
            primary_value = row.get(group_column, "unknown")
            primary_ok = primary_counts.get(primary_value, 0) < max_per_group
        else:
            primary_value = None

        secondary_ok = True
        if secondary_group_column and secondary_max_per_group > 0:
            secondary_value = row.get(secondary_group_column, "unknown")
            secondary_ok = secondary_counts.get(secondary_value, 0) < secondary_max_per_group
        else:
            secondary_value = None

        if not (primary_ok and secondary_ok):
            continue

        selected_rows.append(idx)
        if primary_value is not None:
            primary_counts[primary_value] = primary_counts.get(primary_value, 0) + 1
        if secondary_value is not None:
            secondary_counts[secondary_value] = secondary_counts.get(secondary_value, 0) + 1

    return eligible.loc[selected_rows].copy()


def main() -> int:
    args = parse_args()
    predictions_path = Path(args.predictions_csv)
    if not predictions_path.exists():
        print(f"[ERROR] File not found: {predictions_path}")
        return 1

    df = pd.read_csv(predictions_path, encoding="utf-8-sig")
    if "date" not in df.columns or "symbol" not in df.columns:
        print("[ERROR] Predictions file must include date and symbol columns.")
        return 1

    score_column = detect_score_column(df, args.score_column)
    return_column = detect_return_column(df, args.return_column)
    rebalance_step = args.rebalance_step or infer_horizon_from_return_column(return_column)

    working = df.copy()
    working["symbol"] = working["symbol"].astype(str).str.zfill(6)
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date", score_column, return_column]).copy()

    if args.metadata_csv:
        working = merge_metadata(working, args.metadata_csv)
    working = ensure_group_columns(
        working, [args.group_column, args.secondary_group_column]
    )

    if "close" in working.columns and args.min_close > 0:
        working = working[working["close"] >= args.min_close].copy()
    if "close" in working.columns and args.max_close > 0:
        working = working[working["close"] <= args.max_close].copy()
    if "amount" in working.columns and args.min_amount > 0:
        working = working[working["amount"] >= args.min_amount].copy()

    if args.require_positive_label and "pred_label" in working.columns:
        working = working[working["pred_label"] == 1].copy()

    if working.empty:
        print("[ERROR] No prediction rows remain after filtering.")
        return 1

    rebalance_dates = sorted(working["date"].dt.strftime("%Y-%m-%d").unique())
    rebalance_dates = rebalance_dates[:: max(rebalance_step, 1)]
    periods: list[dict[str, object]] = []
    trade_rows: list[pd.DataFrame] = []

    equity = 1.0
    benchmark_equity = 1.0
    previous_symbols: list[str] = []
    cost_rate = args.transaction_cost_bps / 10000.0

    for rebalance_date in rebalance_dates:
        date_slice = working[working["date"].dt.strftime("%Y-%m-%d") == rebalance_date].copy()
        eligible = date_slice[date_slice[score_column] >= args.min_score].copy()
        if eligible.empty:
            continue

        selected = capped_selection(
            eligible,
            score_column,
            args.top_k,
            args.group_column,
            args.max_per_group,
            args.secondary_group_column,
            args.secondary_max_per_group,
        )
        if selected.empty:
            continue

        current_symbols = selected["symbol"].astype(str).tolist()
        turnover = portfolio_turnover(previous_symbols, current_symbols)
        cost = turnover * cost_rate
        gross_return = float(selected[return_column].mean())
        net_return = gross_return - cost
        benchmark_return = float(date_slice[return_column].mean())
        equity *= 1 + net_return
        benchmark_equity *= 1 + benchmark_return

        selected_to_save = selected.copy()
        selected_to_save["rebalance_date"] = rebalance_date
        selected_to_save["score_column"] = score_column
        selected_to_save["weight"] = 1.0 / len(selected_to_save)
        selected_to_save["turnover"] = turnover
        selected_to_save["transaction_cost"] = cost
        trade_rows.append(selected_to_save)

        periods.append(
            {
                "rebalance_date": rebalance_date,
                "selected_count": int(len(selected)),
                "mean_score": float(selected[score_column].mean()),
                "gross_period_return": gross_return,
                "transaction_cost": cost,
                "turnover": turnover,
                "period_return": net_return,
                "benchmark_return": benchmark_return,
                "excess_return": net_return - benchmark_return,
                "equity": equity,
                "benchmark_equity": benchmark_equity,
            }
        )
        previous_symbols = current_symbols

    if not periods:
        print("[ERROR] Backtest did not produce any rebalance periods.")
        return 1

    periods_df = pd.DataFrame(periods)
    equity_curve = periods_df["equity"]
    benchmark_curve = periods_df["benchmark_equity"]

    rebalances_per_year = 252 / max(rebalance_step, 1)
    total_return = float(equity_curve.iloc[-1] - 1)
    benchmark_total_return = float(benchmark_curve.iloc[-1] - 1)

    summary = {
        "predictions_csv": str(predictions_path),
        "score_column": score_column,
        "return_column": return_column,
        "top_k": args.top_k,
        "rebalance_step": rebalance_step,
        "transaction_cost_bps": args.transaction_cost_bps,
        "group_column": args.group_column,
        "max_per_group": args.max_per_group,
        "secondary_group_column": args.secondary_group_column,
        "secondary_max_per_group": args.secondary_max_per_group,
        "periods": int(len(periods_df)),
        "total_return": total_return,
        "benchmark_total_return": benchmark_total_return,
        "excess_total_return": total_return - benchmark_total_return,
        "mean_period_return": float(periods_df["period_return"].mean()),
        "mean_gross_period_return": float(periods_df["gross_period_return"].mean()),
        "mean_benchmark_return": float(periods_df["benchmark_return"].mean()),
        "mean_turnover": float(periods_df["turnover"].mean()),
        "total_transaction_cost": float(periods_df["transaction_cost"].sum()),
        "win_rate": float((periods_df["period_return"] > 0).mean()),
        "benchmark_win_rate": float((periods_df["benchmark_return"] > 0).mean()),
        "max_drawdown": max_drawdown(equity_curve),
        "benchmark_max_drawdown": max_drawdown(benchmark_curve),
        "annualized_return": annualized_return(total_return, len(periods_df), rebalances_per_year),
        "benchmark_annualized_return": annualized_return(
            benchmark_total_return, len(periods_df), rebalances_per_year
        ),
    }

    output_dir = Path(args.output_dir) if args.output_dir else predictions_path.parent / "backtest_topk"
    output_dir.mkdir(parents=True, exist_ok=True)

    periods_df.to_csv(output_dir / "backtest_periods.csv", index=False, encoding="utf-8")
    if trade_rows:
        pd.concat(trade_rows, ignore_index=True).to_csv(
            output_dir / "selected_trades.csv", index=False, encoding="utf-8"
        )
    (output_dir / "backtest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Backtest periods: {output_dir / 'backtest_periods.csv'}")
    print(f"[OK] Backtest summary: {output_dir / 'backtest_summary.json'}")
    if trade_rows:
        print(f"[OK] Selected trades: {output_dir / 'selected_trades.csv'}")
    print(f"[INFO] Total return: {summary['total_return']:.4f}")
    print(f"[INFO] Benchmark total return: {summary['benchmark_total_return']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
