#!/usr/bin/env python3
"""CLI entrypoint for the white-box risk pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from risk_management.white_box.protocols import strict_white_box_kwargs
from risk_management.white_box.risk_pipeline import run_white_box_risk


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run white-box risk controls on a model prediction file."
    )
    parser.add_argument("predictions_csv", help="Prediction CSV produced by a model module.")
    parser.add_argument("--output-dir", default="", help="Directory used to store risk outputs.")
    parser.add_argument("--model-name", default="", help="Optional model name override.")
    parser.add_argument("--score-column", default="", help="Optional score column override.")
    parser.add_argument("--metadata-csv", default="", help="Optional metadata CSV joined by symbol.")
    parser.add_argument("--rebalance-step", type=int, default=0, help="Rebalance every N dates.")
    parser.add_argument("--top-k", type=int, default=5, help="Maximum selected names per rebalance.")
    parser.add_argument("--min-score", type=float, default=float("-inf"), help="Minimum signal score.")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="Minimum signal confidence.")
    parser.add_argument(
        "--require-positive-label",
        action="store_true",
        help="Require pred_label == 1 when classification labels are present.",
    )
    parser.add_argument("--min-close", type=float, default=0.0, help="Minimum close price.")
    parser.add_argument("--max-close", type=float, default=0.0, help="Maximum close price.")
    parser.add_argument("--min-amount", type=float, default=0.0, help="Minimum成交额.")
    parser.add_argument("--min-turnover", type=float, default=0.0, help="Minimum turnover.")
    parser.add_argument("--min-volume", type=float, default=0.0, help="Minimum volume.")
    parser.add_argument(
        "--min-median-dollar-volume-20",
        type=float,
        default=0.0,
        help="Minimum 20-day median dollar volume.",
    )
    parser.add_argument(
        "--max-vol-20",
        type=float,
        default=0.0,
        help="Maximum 20-day volatility filter. Use 0 to disable.",
    )
    parser.add_argument("--group-column", default="", help="Primary group column, such as industry_group.")
    parser.add_argument("--max-per-group", type=int, default=0, help="Max names per primary group.")
    parser.add_argument(
        "--secondary-group-column",
        default="",
        help="Secondary group column, such as amount_bucket.",
    )
    parser.add_argument(
        "--secondary-max-per-group",
        type=int,
        default=0,
        help="Max names per secondary group.",
    )
    parser.add_argument(
        "--weighting",
        default="equal",
        choices=["equal", "score", "confidence", "score_confidence"],
        help="Position sizing rule.",
    )
    parser.add_argument(
        "--max-position-weight",
        type=float,
        default=1.0,
        help="Maximum weight assigned to a single position.",
    )
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=10.0,
        help="One-way transaction cost in basis points.",
    )
    parser.add_argument(
        "--hold-buffer",
        type=float,
        default=0.0,
        help="Score bonus granted to existing holdings during selection.",
    )
    parser.add_argument(
        "--max-turnover",
        type=float,
        default=0.0,
        help="Maximum portfolio turnover allowed on a rebalance. Use 0 to disable.",
    )
    parser.add_argument(
        "--min-trade-weight",
        type=float,
        default=0.0,
        help="Ignore tiny weight changes smaller than this threshold.",
    )
    parser.add_argument(
        "--sector-neutralization",
        action="store_true",
        help="Neutralize score by sector (score - sector mean score) before ranking.",
    )
    parser.add_argument(
        "--sector-column",
        default="",
        help="Sector column used for neutralization (for example industry_sector).",
    )
    parser.add_argument(
        "--benchmark-symbol",
        default="",
        help="Benchmark symbol used for benchmark return (for example SPY).",
    )
    parser.add_argument(
        "--strict-peer-comparison",
        action="store_true",
        help="Apply frozen P0 strict peer-comparison defaults.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.strict_peer_comparison:
        strict_defaults = strict_white_box_kwargs()
        for field, value in strict_defaults.items():
            setattr(args, field, value)

    result = run_white_box_risk(
        args.predictions_csv,
        output_dir=args.output_dir,
        model_name=args.model_name,
        score_column=args.score_column,
        metadata_csv=args.metadata_csv,
        rebalance_step=args.rebalance_step,
        top_k=args.top_k,
        min_score=args.min_score,
        min_confidence=args.min_confidence,
        require_positive_label=args.require_positive_label,
        min_close=args.min_close,
        max_close=args.max_close,
        min_amount=args.min_amount,
        min_turnover=args.min_turnover,
        min_volume=args.min_volume,
        min_median_dollar_volume_20=args.min_median_dollar_volume_20,
        max_vol_20=args.max_vol_20,
        group_column=args.group_column,
        max_per_group=args.max_per_group,
        secondary_group_column=args.secondary_group_column,
        secondary_max_per_group=args.secondary_max_per_group,
        sector_neutralization=args.sector_neutralization,
        sector_column=args.sector_column,
        weighting=args.weighting,
        max_position_weight=args.max_position_weight,
        transaction_cost_bps=args.transaction_cost_bps,
        hold_buffer=args.hold_buffer,
        max_turnover=args.max_turnover,
        min_trade_weight=args.min_trade_weight,
        benchmark_symbol=args.benchmark_symbol,
    )
    print(f"[OK] Risk periods: {result['periods_path']}")
    print(f"[OK] Risk positions: {result['positions_path']}")
    print(f"[OK] Risk actions: {result['actions_path']}")
    print(f"[OK] Risk summary: {result['summary_path']}")
    print(f"[INFO] Total return: {result['summary']['total_return']:.4f}")
    print(f"[INFO] Benchmark total return: {result['summary']['benchmark_total_return']:.4f}")
    print(f"[INFO] Mean turnover: {result['summary']['mean_turnover']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
