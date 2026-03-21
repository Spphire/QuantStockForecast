#!/usr/bin/env python3
"""Run a batch of U.S. zero-shot white-box risk scenarios and export curve comparisons."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from risk_management.white_box.baselines import (
    build_momentum_predictions,
    build_spy_buy_hold,
    build_universe_equal_weight_buy_hold,
    load_or_fetch_spy_history,
    load_predictions_schedule,
    load_universe_history,
    save_baseline_result,
)
from risk_management.white_box.risk_pipeline import run_white_box_risk


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run several predefined U.S. zero-shot white-box scenarios and compare curves."
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
    metadata = PROJECT_ROOT / "data" / "interim" / "stooq" / "universes" / "us_large_cap_30_metadata.csv"

    scenarios = [
        {
            "name": "regression_balanced",
            "predictions_csv": existing_path(artifacts / "us_zeroshot_regression" / "test_predictions.csv"),
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
            "name": "regression_concentrated",
            "predictions_csv": existing_path(artifacts / "us_zeroshot_regression" / "test_predictions.csv"),
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
            "predictions_csv": existing_path(artifacts / "us_zeroshot_ranking" / "test_predictions.csv"),
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
            "predictions_csv": existing_path(artifacts / "us_zeroshot_ranking" / "test_predictions.csv"),
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
    ]
    return [scenario for scenario in scenarios if scenario["predictions_csv"]]


def default_universe_csv() -> str:
    candidates = [
        PROJECT_ROOT / "data" / "interim" / "stooq" / "universes" / "us_large_cap_30_20200101_20251231_hfq_normalized.csv",
        PROJECT_ROOT / "data" / "interim" / "stooq" / "universes" / "us_large_cap_30_20200101_20260320_hfq_normalized.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


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


def save_curve_plots(
    curve_long: pd.DataFrame,
    output_dir: Path,
    *,
    title_prefix: str,
    filename_prefix: str,
) -> list[Path]:
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
    plt.title(f"{title_prefix} Equity Curves")
    plt.xlabel("Rebalance Date")
    plt.ylabel("Equity")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    equity_path = output_dir / f"{filename_prefix}_equity_curves.png"
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
    plt.title(f"{title_prefix} Drawdown Curves")
    plt.xlabel("Rebalance Date")
    plt.ylabel("Drawdown")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    drawdown_path = output_dir / f"{filename_prefix}_drawdown_curves.png"
    plt.savefig(drawdown_path, dpi=180)
    plt.close()
    plot_paths.append(drawdown_path)

    return plot_paths


def run_reference_baselines(
    *,
    output_dir: Path,
    reference_predictions_csv: str,
    transaction_cost_bps: float,
    regression_balanced_config: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]], list[Path]]:
    universe_csv = default_universe_csv()
    if not universe_csv:
        raise FileNotFoundError("Could not find the U.S. large-cap universe CSV needed for baselines.")

    schedule = load_predictions_schedule(reference_predictions_csv)
    universe_df = load_universe_history(
        universe_csv,
        eval_start=str(schedule["eval_start"]),
        eval_end=str(schedule["eval_end"]),
        horizon=int(schedule["horizon"]),
    )
    spy_df = load_or_fetch_spy_history(
        eval_start=str(schedule["eval_start"]),
        eval_end=str(schedule["eval_end"]),
        horizon=int(schedule["horizon"]),
    )

    baseline_summaries: list[dict[str, object]] = []
    baseline_curves: list[pd.DataFrame] = []
    manifest: list[dict[str, object]] = []

    equal_periods, equal_summary = build_universe_equal_weight_buy_hold(
        universe_df,
        rebalance_dates=list(schedule["rebalance_dates"]),
        rebalance_step=int(schedule["rebalance_step"]),
        transaction_cost_bps=transaction_cost_bps,
        min_close=float(regression_balanced_config.get("min_close", 0.0)),
        min_amount=float(regression_balanced_config.get("min_amount", 0.0)),
    )
    equal_paths = save_baseline_result(output_dir / "universe_equal_weight_buy_hold", equal_periods, equal_summary)
    equal_periods["scenario_name"] = str(equal_summary["baseline_name"])
    equal_periods["benchmark_equity"] = pd.NA
    baseline_curves.append(equal_periods)
    baseline_summaries.append(equal_summary)
    manifest.append(
        {
            "baseline_name": equal_summary["baseline_name"],
            "periods_path": str(equal_paths["periods_path"]),
            "summary_path": str(equal_paths["summary_path"]),
        }
    )

    spy_periods, spy_summary = build_spy_buy_hold(
        spy_df,
        rebalance_dates=list(schedule["rebalance_dates"]),
        rebalance_step=int(schedule["rebalance_step"]),
        transaction_cost_bps=transaction_cost_bps,
    )
    spy_paths = save_baseline_result(output_dir / "spy_buy_hold", spy_periods, spy_summary)
    spy_periods["scenario_name"] = str(spy_summary["baseline_name"])
    spy_periods["benchmark_equity"] = pd.NA
    baseline_curves.append(spy_periods)
    baseline_summaries.append(spy_summary)
    manifest.append(
        {
            "baseline_name": spy_summary["baseline_name"],
            "periods_path": str(spy_paths["periods_path"]),
            "summary_path": str(spy_paths["summary_path"]),
        }
    )

    momentum_predictions_path = build_momentum_predictions(
        universe_df,
        output_csv=output_dir / "momentum_topk_20d" / "momentum_predictions.csv",
        horizon=int(schedule["horizon"]),
    )
    momentum_result = run_white_box_risk(
        str(momentum_predictions_path),
        output_dir=output_dir / "momentum_topk_20d",
        model_name="momentum_20d",
        score_column="pred_return",
        metadata_csv=str(regression_balanced_config.get("metadata_csv", "")),
        rebalance_step=int(schedule["rebalance_step"]),
        top_k=int(regression_balanced_config.get("top_k", 5)),
        min_score=float("-inf"),
        min_confidence=0.0,
        min_close=float(regression_balanced_config.get("min_close", 0.0)),
        min_amount=float(regression_balanced_config.get("min_amount", 0.0)),
        group_column=str(regression_balanced_config.get("group_column", "")),
        max_per_group=int(regression_balanced_config.get("max_per_group", 0)),
        secondary_group_column=str(regression_balanced_config.get("secondary_group_column", "")),
        secondary_max_per_group=int(regression_balanced_config.get("secondary_max_per_group", 0)),
        weighting="equal",
        max_position_weight=float(regression_balanced_config.get("max_position_weight", 0.35)),
        transaction_cost_bps=transaction_cost_bps,
    )
    momentum_summary = dict(momentum_result["summary"])
    momentum_summary["baseline_name"] = "momentum_topk_20d"
    momentum_summary["baseline_type"] = "rule_based"
    momentum_summary["description"] = (
        "Select the top 5 names by trailing 20-day return, equal-weighted, "
        "with the same liquidity and group constraints."
    )
    baseline_summaries.append(momentum_summary)
    momentum_periods = pd.read_csv(momentum_result["periods_path"], encoding="utf-8-sig")
    momentum_periods["scenario_name"] = str(momentum_summary["baseline_name"])
    baseline_curves.append(momentum_periods)
    manifest.append(
        {
            "baseline_name": momentum_summary["baseline_name"],
            "periods_path": str(momentum_result["periods_path"]),
            "summary_path": str(momentum_result["summary_path"]),
            "predictions_path": str(momentum_predictions_path),
        }
    )

    baseline_summary_df = pd.DataFrame(baseline_summaries).sort_values(
        ["total_return", "annualized_return"],
        ascending=[False, False],
        kind="stable",
    )
    baseline_curves = [frame for frame in baseline_curves if not frame.empty]
    baseline_curve_df = pd.concat(baseline_curves, ignore_index=True) if baseline_curves else pd.DataFrame()
    plot_paths = save_curve_plots(
        baseline_curve_df,
        output_dir,
        title_prefix="U.S. Zero-Shot Baseline",
        filename_prefix="baseline",
    )
    return baseline_summary_df, baseline_curve_df, manifest, plot_paths


def main() -> int:
    args = parse_args()
    scenarios = default_scenarios(args.transaction_cost_bps)
    if not scenarios:
        print("[ERROR] No default U.S. zero-shot scenarios are available. Prepare prediction artifacts first.")
        return 1

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else PROJECT_ROOT / "risk_management" / "white_box" / "experiments" / "us_zeroshot_suite"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    curve_rows: list[pd.DataFrame] = []
    action_rows: list[pd.DataFrame] = []
    manifest: list[dict[str, object]] = []
    reference_predictions_csv = ""
    regression_balanced_config: dict[str, object] = {}

    for scenario in scenarios:
        scenario_name = str(scenario["name"])
        scenario_kwargs = {key: value for key, value in scenario.items() if key != "name"}
        predictions_csv = str(scenario_kwargs["predictions_csv"])
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
        if scenario_name == "regression_balanced":
            reference_predictions_csv = predictions_csv
            regression_balanced_config = dict(scenario)
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
    plot_paths = save_curve_plots(
        curve_long_df,
        output_dir,
        title_prefix="U.S. Zero-Shot White-Box",
        filename_prefix="scenario",
    )

    baseline_summary_df = pd.DataFrame()
    baseline_curve_df = pd.DataFrame()
    baseline_manifest: list[dict[str, object]] = []
    baseline_plot_paths: list[Path] = []
    if reference_predictions_csv and regression_balanced_config:
        baseline_summary_df, baseline_curve_df, baseline_manifest, baseline_plot_paths = run_reference_baselines(
            output_dir=output_dir,
            reference_predictions_csv=reference_predictions_csv,
            transaction_cost_bps=args.transaction_cost_bps,
            regression_balanced_config=regression_balanced_config,
        )

    comparison_summary_df = summary_df.copy()
    comparison_summary_df["comparison_group"] = "model_scenario"
    comparison_summary_df["comparison_name"] = comparison_summary_df["scenario_name"]
    if not baseline_summary_df.empty:
        baseline_summary_copy = baseline_summary_df.copy()
        baseline_summary_copy["comparison_group"] = "baseline"
        baseline_summary_copy["comparison_name"] = baseline_summary_copy["baseline_name"]
        comparison_summary_df = pd.concat(
            [comparison_summary_df, baseline_summary_copy],
            ignore_index=True,
            sort=False,
        )

    comparison_curve_df = curve_long_df.copy()
    if not comparison_curve_df.empty:
        comparison_curve_df["comparison_group"] = "model_scenario"
        comparison_curve_df["comparison_name"] = comparison_curve_df["scenario_name"]
    if not baseline_curve_df.empty:
        baseline_curve_copy = baseline_curve_df.copy()
        baseline_curve_copy["comparison_group"] = "baseline"
        baseline_curve_copy["comparison_name"] = baseline_curve_copy["scenario_name"]
        comparison_curve_df = pd.concat(
            [comparison_curve_df, baseline_curve_copy],
            ignore_index=True,
            sort=False,
        )

    if not comparison_curve_df.empty:
        equity_input_df = comparison_curve_df.copy()
        if "comparison_name" in equity_input_df.columns:
            equity_input_df["scenario_name"] = equity_input_df["comparison_name"]
        comparison_equity_wide_df = build_equity_wide(equity_input_df)
    else:
        comparison_equity_wide_df = pd.DataFrame()

    summary_df.to_csv(output_dir / "scenario_comparison.csv", index=False, encoding="utf-8")
    curve_long_df.to_csv(output_dir / "curve_comparison_long.csv", index=False, encoding="utf-8")
    equity_wide_df.to_csv(output_dir / "equity_curve_wide.csv", index=False, encoding="utf-8")
    actions_long_df.to_csv(output_dir / "action_comparison_long.csv", index=False, encoding="utf-8")
    action_summary_df.to_csv(output_dir / "action_comparison.csv", index=False, encoding="utf-8")
    baseline_summary_df.to_csv(output_dir / "baseline_comparison.csv", index=False, encoding="utf-8")
    baseline_curve_df.to_csv(output_dir / "baseline_curve_comparison_long.csv", index=False, encoding="utf-8")
    comparison_summary_df.to_csv(
        output_dir / "comparison_with_baselines.csv", index=False, encoding="utf-8"
    )
    comparison_curve_df.to_csv(
        output_dir / "curve_comparison_with_baselines_long.csv", index=False, encoding="utf-8"
    )
    comparison_equity_wide_df.to_csv(
        output_dir / "equity_curve_with_baselines_wide.csv", index=False, encoding="utf-8"
    )
    (output_dir / "suite_manifest.json").write_text(
        json.dumps(manifest + baseline_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[OK] Scenario comparison: {output_dir / 'scenario_comparison.csv'}")
    print(f"[OK] Baseline comparison: {output_dir / 'baseline_comparison.csv'}")
    print(f"[OK] Comparison with baselines: {output_dir / 'comparison_with_baselines.csv'}")
    print(f"[OK] Curve comparison: {output_dir / 'curve_comparison_long.csv'}")
    print(f"[OK] Equity wide table: {output_dir / 'equity_curve_wide.csv'}")
    print(f"[OK] Action comparison: {output_dir / 'action_comparison.csv'}")
    for plot_path in plot_paths + baseline_plot_paths:
        print(f"[OK] Plot: {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
