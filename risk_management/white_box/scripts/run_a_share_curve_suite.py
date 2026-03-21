#!/usr/bin/env python3
"""Run a batch of A-share white-box risk scenarios and export curve comparisons."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from risk_management.white_box.risk_pipeline import run_white_box_risk


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run several predefined A-share white-box scenarios and compare curves."
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory used to store scenario outputs and comparison tables.",
    )
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=10.0,
        help="One-way transaction cost shared by all scenarios.",
    )
    return parser.parse_args()


def existing_path(path: Path) -> str:
    return str(path) if path.exists() else ""


def default_scenarios(transaction_cost_bps: float) -> list[dict[str, object]]:
    artifacts = PROJECT_ROOT / "model_prediction" / "lightgbm" / "artifacts"
    metadata = PROJECT_ROOT / "data" / "interim" / "akshare" / "universes" / "large_cap_50_metadata.csv"

    scenarios = [
        {
            "name": "regression_equal",
            "predictions_csv": existing_path(
                artifacts
                / "large_cap_50_20200101_20241231_hfq_normalized_regression_5d"
                / "test_predictions.csv"
            ),
            "metadata_csv": existing_path(metadata),
            "top_k": 5,
            "min_score": 0.0,
            "min_confidence": 0.0,
            "min_close": 5.0,
            "min_amount": 100000000.0,
            "group_column": "industry_group",
            "max_per_group": 1,
            "secondary_group_column": "amount_bucket",
            "secondary_max_per_group": 2,
            "weighting": "equal",
            "max_position_weight": 0.35,
            "transaction_cost_bps": transaction_cost_bps,
        },
        {
            "name": "regression_balanced",
            "predictions_csv": existing_path(
                artifacts
                / "large_cap_50_20200101_20241231_hfq_normalized_regression_5d"
                / "test_predictions.csv"
            ),
            "metadata_csv": existing_path(metadata),
            "top_k": 5,
            "min_score": 0.0,
            "min_confidence": 0.7,
            "min_close": 5.0,
            "min_amount": 100000000.0,
            "group_column": "industry_group",
            "max_per_group": 1,
            "secondary_group_column": "amount_bucket",
            "secondary_max_per_group": 2,
            "weighting": "score_confidence",
            "max_position_weight": 0.35,
            "transaction_cost_bps": transaction_cost_bps,
        },
        {
            "name": "regression_smoothed",
            "predictions_csv": existing_path(
                artifacts
                / "large_cap_50_20200101_20241231_hfq_normalized_regression_5d"
                / "test_predictions.csv"
            ),
            "metadata_csv": existing_path(metadata),
            "top_k": 5,
            "min_score": 0.0,
            "min_confidence": 0.7,
            "min_close": 5.0,
            "min_amount": 100000000.0,
            "group_column": "industry_group",
            "max_per_group": 1,
            "secondary_group_column": "amount_bucket",
            "secondary_max_per_group": 2,
            "weighting": "score_confidence",
            "max_position_weight": 0.35,
            "transaction_cost_bps": transaction_cost_bps,
            "hold_buffer": 0.001,
            "max_turnover": 0.4,
            "min_trade_weight": 0.03,
        },
        {
            "name": "regression_smoothed_strict",
            "predictions_csv": existing_path(
                artifacts
                / "large_cap_50_20200101_20241231_hfq_normalized_regression_5d"
                / "test_predictions.csv"
            ),
            "metadata_csv": existing_path(metadata),
            "top_k": 5,
            "min_score": 0.0,
            "min_confidence": 0.75,
            "min_close": 5.0,
            "min_amount": 100000000.0,
            "group_column": "industry_group",
            "max_per_group": 1,
            "secondary_group_column": "amount_bucket",
            "secondary_max_per_group": 2,
            "weighting": "score_confidence",
            "max_position_weight": 0.35,
            "transaction_cost_bps": transaction_cost_bps,
            "hold_buffer": 0.0015,
            "max_turnover": 0.3,
            "min_trade_weight": 0.04,
        },
        {
            "name": "regression_concentrated",
            "predictions_csv": existing_path(
                artifacts
                / "large_cap_50_20200101_20241231_hfq_normalized_regression_5d"
                / "test_predictions.csv"
            ),
            "metadata_csv": existing_path(metadata),
            "top_k": 3,
            "min_score": 0.002,
            "min_confidence": 0.85,
            "min_close": 5.0,
            "min_amount": 100000000.0,
            "group_column": "industry_group",
            "max_per_group": 1,
            "secondary_group_column": "amount_bucket",
            "secondary_max_per_group": 2,
            "weighting": "score_confidence",
            "max_position_weight": 0.5,
            "transaction_cost_bps": transaction_cost_bps,
        },
        {
            "name": "ranking_balanced",
            "predictions_csv": existing_path(
                artifacts
                / "large_cap_50_20200101_20241231_hfq_normalized_ranking_5d"
                / "test_predictions.csv"
            ),
            "metadata_csv": existing_path(metadata),
            "top_k": 5,
            "min_confidence": 0.7,
            "min_close": 5.0,
            "min_amount": 100000000.0,
            "group_column": "industry_group",
            "max_per_group": 1,
            "secondary_group_column": "amount_bucket",
            "secondary_max_per_group": 2,
            "weighting": "confidence",
            "max_position_weight": 0.35,
            "transaction_cost_bps": transaction_cost_bps,
        },
        {
            "name": "ranking_smoothed",
            "predictions_csv": existing_path(
                artifacts
                / "large_cap_50_20200101_20241231_hfq_normalized_ranking_5d"
                / "test_predictions.csv"
            ),
            "metadata_csv": existing_path(metadata),
            "top_k": 5,
            "min_confidence": 0.7,
            "min_close": 5.0,
            "min_amount": 100000000.0,
            "group_column": "industry_group",
            "max_per_group": 1,
            "secondary_group_column": "amount_bucket",
            "secondary_max_per_group": 2,
            "weighting": "confidence",
            "max_position_weight": 0.35,
            "transaction_cost_bps": transaction_cost_bps,
            "hold_buffer": 0.03,
            "max_turnover": 0.5,
            "min_trade_weight": 0.02,
        },
        {
            "name": "classification_guarded",
            "predictions_csv": existing_path(
                artifacts
                / "large_cap_20200101_20241231_hfq_normalized_classification_5d"
                / "test_predictions.csv"
            ),
            "metadata_csv": "",
            "top_k": 3,
            "min_confidence": 0.7,
            "require_positive_label": True,
            "weighting": "confidence",
            "max_position_weight": 0.5,
            "transaction_cost_bps": transaction_cost_bps,
        },
    ]
    return [scenario for scenario in scenarios if scenario["predictions_csv"]]


def scenario_output_dir(base_output_dir: Path, name: str) -> Path:
    return base_output_dir / name


def build_equity_wide(curve_long: pd.DataFrame) -> pd.DataFrame:
    equity = curve_long.pivot_table(
        index="rebalance_date",
        columns="scenario_name",
        values="equity",
        aggfunc="last",
    )
    equity.columns = [f"{column}_equity" for column in equity.columns]

    benchmark = curve_long.pivot_table(
        index="rebalance_date",
        columns="scenario_name",
        values="benchmark_equity",
        aggfunc="last",
    )
    benchmark.columns = [f"{column}_benchmark" for column in benchmark.columns]
    return equity.join(benchmark, how="outer").reset_index()


def build_action_summary(actions_long: pd.DataFrame) -> pd.DataFrame:
    if actions_long.empty:
        return pd.DataFrame()

    grouped = actions_long.groupby(["scenario_name", "action"], dropna=False).agg(
        action_count=("symbol", "size"),
        total_abs_weight_change=("abs_weight_change", "sum"),
        mean_abs_weight_change=("abs_weight_change", "mean"),
        total_weight_change=("weight_change", "sum"),
    )
    return grouped.reset_index().sort_values(["scenario_name", "action"], kind="stable")


def save_curve_plots(curve_long: pd.DataFrame, output_dir: Path) -> list[Path]:
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return []

    if curve_long.empty:
        return []

    working = curve_long.copy()
    working["rebalance_date"] = pd.to_datetime(working["rebalance_date"], errors="coerce")
    working = working.dropna(subset=["rebalance_date"]).sort_values(
        ["scenario_name", "rebalance_date"], kind="stable"
    )

    plot_paths: list[Path] = []

    plt.figure(figsize=(12, 7))
    for scenario_name, scenario_df in working.groupby("scenario_name", sort=False):
        plt.plot(
            scenario_df["rebalance_date"],
            scenario_df["equity"],
            label=str(scenario_name),
            linewidth=2,
        )
    plt.title("A-share White-Box Equity Curves")
    plt.xlabel("Rebalance Date")
    plt.ylabel("Equity")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    equity_path = output_dir / "equity_curves.png"
    plt.savefig(equity_path, dpi=180)
    plt.close()
    plot_paths.append(equity_path)

    plt.figure(figsize=(12, 7))
    for scenario_name, scenario_df in working.groupby("scenario_name", sort=False):
        running_max = scenario_df["equity"].cummax()
        drawdown = scenario_df["equity"] / running_max - 1.0
        plt.plot(
            scenario_df["rebalance_date"],
            drawdown,
            label=str(scenario_name),
            linewidth=2,
        )
    plt.title("A-share White-Box Drawdown Curves")
    plt.xlabel("Rebalance Date")
    plt.ylabel("Drawdown")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    drawdown_path = output_dir / "drawdown_curves.png"
    plt.savefig(drawdown_path, dpi=180)
    plt.close()
    plot_paths.append(drawdown_path)

    return plot_paths


def main() -> int:
    args = parse_args()
    scenarios = default_scenarios(args.transaction_cost_bps)
    if not scenarios:
        print("[ERROR] No default scenarios are available. Prepare prediction artifacts first.")
        return 1

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else PROJECT_ROOT / "risk_management" / "white_box" / "experiments" / "a_share_curve_suite"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    curve_rows: list[pd.DataFrame] = []
    action_rows: list[pd.DataFrame] = []
    manifest: list[dict[str, object]] = []

    for scenario in scenarios:
        scenario_name = str(scenario["name"])
        scenario_kwargs = {key: value for key, value in scenario.items() if key != "name"}
        result = run_white_box_risk(
            scenario_kwargs.pop("predictions_csv"),
            output_dir=scenario_output_dir(output_dir, scenario_name),
            **scenario_kwargs,
        )
        summary = dict(result["summary"])
        summary["scenario_name"] = scenario_name
        summaries.append(summary)

        periods_df = pd.read_csv(result["periods_path"], encoding="utf-8-sig")
        periods_df["scenario_name"] = scenario_name
        curve_rows.append(periods_df)

        actions_df = pd.read_csv(result["actions_path"], encoding="utf-8-sig")
        actions_df["scenario_name"] = scenario_name
        action_rows.append(actions_df)

        manifest.append(
            {
                "scenario_name": scenario_name,
                "periods_path": str(result["periods_path"]),
                "positions_path": str(result["positions_path"]),
                "actions_path": str(result["actions_path"]),
                "summary_path": str(result["summary_path"]),
            }
        )
        print(
            f"[OK] {scenario_name}: total_return={summary['total_return']:.4f}, "
            f"max_drawdown={summary['max_drawdown']:.4f}, add_actions={summary['total_add_actions']}"
        )

    summary_df = pd.DataFrame(summaries).sort_values(
        ["excess_total_return", "annualized_return"],
        ascending=[False, False],
        kind="stable",
    )
    curve_long_df = pd.concat(curve_rows, ignore_index=True) if curve_rows else pd.DataFrame()
    actions_long_df = pd.concat(action_rows, ignore_index=True) if action_rows else pd.DataFrame()
    equity_wide_df = build_equity_wide(curve_long_df) if not curve_long_df.empty else pd.DataFrame()
    action_summary_df = build_action_summary(actions_long_df)
    plot_paths = save_curve_plots(curve_long_df, output_dir)

    summary_df.to_csv(output_dir / "scenario_comparison.csv", index=False, encoding="utf-8")
    curve_long_df.to_csv(output_dir / "curve_comparison_long.csv", index=False, encoding="utf-8")
    equity_wide_df.to_csv(output_dir / "equity_curve_wide.csv", index=False, encoding="utf-8")
    actions_long_df.to_csv(output_dir / "action_comparison_long.csv", index=False, encoding="utf-8")
    action_summary_df.to_csv(output_dir / "action_comparison.csv", index=False, encoding="utf-8")
    (output_dir / "suite_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Scenario comparison: {output_dir / 'scenario_comparison.csv'}")
    print(f"[OK] Curve comparison: {output_dir / 'curve_comparison_long.csv'}")
    print(f"[OK] Equity wide table: {output_dir / 'equity_curve_wide.csv'}")
    print(f"[OK] Action comparison: {output_dir / 'action_comparison.csv'}")
    for plot_path in plot_paths:
        print(f"[OK] Plot: {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
