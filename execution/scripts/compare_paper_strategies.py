#!/usr/bin/env python3
"""Compare two execution strategy configs using upstream summaries and latest plans."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two paper-trading strategy configs and their latest upstream results."
    )
    parser.add_argument("strategy_a", help="Path to the first strategy JSON config.")
    parser.add_argument("strategy_b", help="Path to the second strategy JSON config.")
    parser.add_argument(
        "--output-csv",
        default="",
        help="Optional path for the comparison CSV.",
    )
    return parser.parse_args()


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_rebalance_stats(risk_positions_path: str) -> dict[str, object]:
    df = pd.read_csv(risk_positions_path, encoding="utf-8-sig")
    latest_date = str(df["rebalance_date"].max())
    latest = df[df["rebalance_date"].astype(str) == latest_date].copy()
    return {
        "latest_rebalance_date": latest_date,
        "latest_target_count": int(len(latest)),
        "latest_weight_sum": float(pd.to_numeric(latest["target_weight"], errors="coerce").fillna(0.0).sum()),
        "latest_mean_confidence": float(pd.to_numeric(latest["confidence"], errors="coerce").fillna(0.0).mean()),
        "latest_mean_score": float(pd.to_numeric(latest["score"], errors="coerce").fillna(0.0).mean()),
    }


def summarize_strategy(config_path: str | Path) -> dict[str, object]:
    config = load_json(config_path)
    source = dict(config["source"])
    execution = dict(config.get("execution", {}))
    summary = load_json(source["summary_path"])
    latest = latest_rebalance_stats(source["path"])
    return {
        "strategy_id": config["strategy_id"],
        "description": config.get("description", ""),
        "paper_env_prefix": config.get("paper_env_prefix", ""),
        "source_path": source["path"],
        "summary_path": source["summary_path"],
        "total_return": summary.get("total_return"),
        "excess_total_return": summary.get("excess_total_return"),
        "max_drawdown": summary.get("max_drawdown"),
        "annualized_return": summary.get("annualized_return"),
        "mean_turnover": summary.get("mean_turnover"),
        "latest_rebalance_date": latest["latest_rebalance_date"],
        "latest_target_count": latest["latest_target_count"],
        "latest_weight_sum": latest["latest_weight_sum"],
        "latest_mean_confidence": latest["latest_mean_confidence"],
        "latest_mean_score": latest["latest_mean_score"],
        "max_position_weight": execution.get("max_position_weight"),
        "allow_fractional": execution.get("allow_fractional"),
        "default_account_equity": execution.get("default_account_equity"),
    }


def main() -> int:
    args = parse_args()
    rows = [
        summarize_strategy(args.strategy_a),
        summarize_strategy(args.strategy_b),
    ]
    df = pd.DataFrame(rows)

    output_path = (
        Path(args.output_csv)
        if args.output_csv
        else PROJECT_ROOT / "execution" / "runtime" / "strategy_comparison.csv"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8")

    print(f"[OK] Strategy comparison: {output_path}")
    for row in rows:
        print(
            f"[INFO] {row['strategy_id']}: total_return={float(row['total_return']):.4f}, "
            f"excess={float(row['excess_total_return']):.4f}, latest_targets={row['latest_target_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
