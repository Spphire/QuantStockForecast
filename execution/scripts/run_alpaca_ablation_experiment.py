#!/usr/bin/env python3
"""Run the Alpaca-style ablation pipeline across fixed datasets and strategies."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


BASE_EXPERTS = ["lightgbm", "xgboost", "catboost", "lstm", "transformer"]
ALL_STRATEGIES = [*BASE_EXPERTS, "ensemble_vote"]
DATASET_IDS = ["d1_a_share_only", "d2_a_share_plus_us"]
PRIMARY_SUMMARY_KEYS = [
    "sessions",
    "total_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe",
    "max_drawdown",
    "benchmark_total_return",
    "mean_turnover",
    "mean_cost_bps",
]


class StepError(RuntimeError):
    """Raised when one pipeline step fails."""


@dataclass(slots=True)
class TrainingArtifact:
    dataset_id: str
    expert: str
    output_dir: Path
    model_path: Path
    metrics_path: Path


def first_existing_path(candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    for candidate in reversed(candidates):
        if not candidate:
            return candidate
    return candidates[0] if candidates else ""


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def build_default_run_id() -> str:
    return f"alpaca_ablation_{datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')}"


def resolve_path(raw_path: str, *, allow_empty: bool = False) -> Path:
    value = str(raw_path or "").strip()
    if not value:
        if allow_empty:
            return Path()
        raise ValueError("A required path argument was empty.")
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


def ensure_file(path: Path, *, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    if path.is_dir():
        raise FileNotFoundError(f"{label} must be a file, got directory: {path}")
    return path


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def format_command(command: list[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def run_subprocess(command: list[str], *, log_path: Path, cwd: Path = PROJECT_ROOT) -> None:
    ensure_parent(log_path)
    result = subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    log_text = f"$ {format_command(command)}\n\n{result.stdout or ''}"
    log_path.write_text(log_text, encoding="utf-8")
    if result.returncode != 0:
        tail_lines = (result.stdout or "").splitlines()[-40:]
        tail = "\n".join(tail_lines)
        raise StepError(
            f"Command failed with exit code {result.returncode}: {format_command(command)}\n"
            f"Log: {log_path}\n"
            f"{tail}"
        )


def maybe_add_arg(command: list[str], flag: str, value: str | Path | None) -> None:
    if value is None:
        return
    rendered = str(value)
    if not rendered:
        return
    command.extend([flag, rendered])


def float_or_zero(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(numeric) or math.isinf(numeric):
        return 0.0
    return numeric


def mean_cost_bps_from_periods(periods_df: pd.DataFrame) -> float:
    if periods_df.empty or "transaction_cost" not in periods_df.columns:
        return 0.0
    if "account_equity_start" not in periods_df.columns:
        return 0.0
    costs = pd.to_numeric(periods_df["transaction_cost"], errors="coerce").fillna(0.0)
    equity = pd.to_numeric(periods_df["account_equity_start"], errors="coerce").replace(0.0, pd.NA)
    cost_bps = (costs / equity) * 10000.0
    cost_bps = cost_bps.dropna()
    return float(cost_bps.mean()) if not cost_bps.empty else 0.0


def annualized_volatility(period_returns: pd.Series, rebalance_step: int) -> float:
    if period_returns.empty:
        return 0.0
    std = float(period_returns.std(ddof=0))
    if std <= 0:
        return 0.0
    rebalances_per_year = 252.0 / max(int(rebalance_step), 1)
    return std * math.sqrt(rebalances_per_year)


def sharpe_ratio(period_returns: pd.Series, rebalance_step: int) -> float:
    if period_returns.empty:
        return 0.0
    std = float(period_returns.std(ddof=0))
    if std <= 0:
        return 0.0
    mean = float(period_returns.mean())
    rebalances_per_year = 252.0 / max(int(rebalance_step), 1)
    return mean / std * math.sqrt(rebalances_per_year)


def compute_primary_summary(
    *,
    execution_summary_path: Path,
    risk_summary_path: Path,
    execution_periods_path: Path,
    rebalance_step: int,
) -> dict[str, float | int]:
    execution_summary = read_json(execution_summary_path)
    risk_summary = read_json(risk_summary_path)
    periods_df = pd.read_csv(execution_periods_path, encoding="utf-8-sig")
    period_returns = pd.to_numeric(periods_df.get("period_return"), errors="coerce").dropna()
    return {
        "sessions": int(execution_summary.get("rebalance_count") or len(periods_df)),
        "total_return": float_or_zero(execution_summary.get("total_return")),
        "annualized_return": float_or_zero(execution_summary.get("annualized_return")),
        "annualized_volatility": annualized_volatility(period_returns, rebalance_step),
        "sharpe": sharpe_ratio(period_returns, rebalance_step),
        "max_drawdown": float_or_zero(execution_summary.get("max_drawdown")),
        "benchmark_total_return": float_or_zero(
            execution_summary.get("benchmark_total_return", risk_summary.get("benchmark_total_return"))
        ),
        "mean_turnover": float_or_zero(risk_summary.get("mean_turnover")),
        "mean_cost_bps": mean_cost_bps_from_periods(periods_df),
    }


def expected_model_path(output_dir: Path, expert: str) -> Path:
    filenames = {
        "lightgbm": "model.txt",
        "xgboost": "model.json",
        "catboost": "model.cbm",
        "lstm": "model.pt",
        "transformer": "model.pt",
    }
    return output_dir / filenames[expert]


def load_model_path(output_dir: Path, expert: str) -> Path:
    metrics_path = output_dir / "metrics.json"
    if metrics_path.exists():
        payload = read_json(metrics_path)
        for block in [payload, payload.get("metrics") if isinstance(payload.get("metrics"), dict) else None]:
            if not isinstance(block, dict):
                continue
            candidate = str(block.get("model_path", "")).strip()
            if candidate:
                resolved = resolve_path(candidate)
                if resolved.exists():
                    return resolved
    fallback = expected_model_path(output_dir, expert)
    ensure_file(fallback, label=f"{expert} model artifact")
    return fallback


def train_artifacts_exist(output_dir: Path, expert: str) -> bool:
    return (output_dir / "metrics.json").exists() and expected_model_path(output_dir, expert).exists()


def prediction_artifact_path(output_dir: Path) -> Path:
    return output_dir / "test_predictions.csv"


def risk_artifact_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "positions": output_dir / "risk_positions.csv",
        "periods": output_dir / "risk_periods.csv",
        "summary": output_dir / "risk_summary.json",
    }


def execution_artifact_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "periods": output_dir / "execution_periods.csv",
        "summary": output_dir / "execution_summary.json",
        "primary": output_dir / "primary_summary.json",
    }

def dataset_specs(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    return {
        "d1_a_share_only": {
            "name": "D1 A-share Only",
            "train_csv": resolve_path(args.a_share_dataset),
            "price_provider_label": args.a_share_price_provider_label,
            "price_source_label": args.a_share_price_source_label,
            "price_origin_url": args.a_share_price_origin_url,
            "metadata_provider_label": args.a_share_metadata_provider_label,
            "metadata_source_label": args.a_share_metadata_source_label,
            "metadata_origin_url": args.a_share_metadata_origin_url,
            "symbols_file": str(resolve_path(args.a_share_symbols_file)),
        },
        "d2_a_share_plus_us": {
            "name": "D2 A-share Plus US",
            "train_csv": resolve_path(args.a_share_plus_us_dataset),
            "price_provider_label": args.us_price_provider_label,
            "price_source_label": args.us_price_source_label,
            "price_origin_url": args.us_price_origin_url,
            "metadata_provider_label": args.us_metadata_provider_label,
            "metadata_source_label": args.us_metadata_source_label,
            "metadata_origin_url": args.us_metadata_origin_url,
            "symbols_file": str(resolve_path(args.us_symbols_file)),
        },
    }


def build_data_origins_payload(
    args: argparse.Namespace,
    *,
    run_id: str,
    experiment_dir: Path,
    datasets: dict[str, dict[str, Any]],
    eval_universe: Path,
    execution_universe: Path,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "generated_at": iso_now(),
        "project_root": str(PROJECT_ROOT),
        "experiment_dir": str(experiment_dir),
        "source_manifest_path": str(resolve_path(args.source_manifest_path, allow_empty=True)) if args.source_manifest_path else "",
        "source_fetched_at": args.source_fetched_at or "",
        "evaluation_window": {
            "eval_start": args.eval_start,
            "eval_end": args.eval_end,
            "benchmark_symbol": args.risk_benchmark_symbol,
        },
        "datasets": {
            dataset_id: {
                "dataset_id": dataset_id,
                "name": spec["name"],
                "train_csv": str(spec["train_csv"]),
                "symbols_file": spec["symbols_file"],
                "price_provider_label": spec["price_provider_label"],
                "price_source_label": spec["price_source_label"],
                "price_origin_url": spec["price_origin_url"],
                "metadata_provider_label": spec["metadata_provider_label"],
                "metadata_source_label": spec["metadata_source_label"],
                "metadata_origin_url": spec["metadata_origin_url"],
            }
            for dataset_id, spec in datasets.items()
        },
        "evaluation_inputs": {
            "predict_eval_universe_csv": str(eval_universe),
            "execution_universe_csv": str(execution_universe),
            "metadata_csv": str(resolve_path(args.risk_metadata_csv, allow_empty=True)) if args.risk_metadata_csv else "",
            "us_price_provider_label": args.us_price_provider_label,
            "us_price_source_label": args.us_price_source_label,
            "us_price_origin_url": args.us_price_origin_url,
            "us_alpaca_feed": args.us_alpaca_feed,
            "us_alpaca_adjustment": args.us_alpaca_adjustment,
            "us_metadata_provider_label": args.us_metadata_provider_label,
            "us_metadata_source_label": args.us_metadata_source_label,
            "us_metadata_origin_url": args.us_metadata_origin_url,
        },
    }


def build_train_command(*, expert: str, input_csv: Path, output_dir: Path, args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "model_prediction" / "common" / "run_expert_model.py"),
        "train",
        expert,
        "--",
        str(input_csv),
        "--output-dir",
        str(output_dir),
        "--mode",
        args.model_mode,
        "--horizon",
        str(args.horizon),
        "--train-ratio",
        str(args.train_ratio),
        "--valid-ratio",
        str(args.valid_ratio),
    ]
    if expert == "lstm":
        command.extend(["--seed", str(args.seed)])
        maybe_add_arg(command, "--device", args.torch_device)
    if expert == "transformer":
        maybe_add_arg(command, "--device", args.torch_device)
    return command


def build_predict_command(
    *,
    expert: str,
    input_csv: Path,
    model_path: Path,
    metrics_path: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "model_prediction" / "common" / "run_expert_model.py"),
        "predict",
        expert,
        "--",
        str(input_csv),
        "--model-path",
        str(model_path),
        "--reference-metrics",
        str(metrics_path),
        "--output-dir",
        str(output_dir),
        "--eval-start",
        args.eval_start,
        "--eval-end",
        args.eval_end,
    ]
    if expert == "lstm":
        maybe_add_arg(command, "--device", args.torch_device)
    return command


def build_ensemble_command(*, prediction_csvs: list[Path], output_dir: Path) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "model_prediction" / "ensemble" / "scripts" / "predict_ensemble.py"),
        str(prediction_csvs[0]),
    ]
    for path in prediction_csvs[1:]:
        command.extend(["--prediction-csv", str(path)])
    command.extend(
        [
            "--method",
            "mean_score",
            "--min-experts",
            "5",
            "--model-name",
            "ensemble_mean_score",
            "--output-dir",
            str(output_dir),
        ]
    )
    return command


def build_risk_command(
    *,
    predictions_csv: Path,
    output_dir: Path,
    strategy_name: str,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "risk_management" / "white_box" / "scripts" / "run_white_box_risk.py"),
        str(predictions_csv),
        "--output-dir",
        str(output_dir),
        "--model-name",
        strategy_name,
        "--rebalance-step",
        str(args.risk_rebalance_step),
        "--top-k",
        str(args.risk_top_k),
        "--min-score",
        str(args.risk_min_score),
        "--min-confidence",
        str(args.risk_min_confidence),
        "--min-close",
        str(args.risk_min_close),
        "--max-close",
        str(args.risk_max_close),
        "--min-amount",
        str(args.risk_min_amount),
        "--min-turnover",
        str(args.risk_min_turnover),
        "--min-volume",
        str(args.risk_min_volume),
        "--min-median-dollar-volume-20",
        str(args.risk_min_median_dollar_volume_20),
        "--max-vol-20",
        str(args.risk_max_vol_20),
        "--group-column",
        args.risk_group_column,
        "--max-per-group",
        str(args.risk_max_per_group),
        "--secondary-group-column",
        args.risk_secondary_group_column,
        "--secondary-max-per-group",
        str(args.risk_secondary_max_per_group),
        "--weighting",
        args.risk_weighting,
        "--max-position-weight",
        str(args.risk_max_position_weight),
        "--max-gross-exposure",
        str(args.risk_max_gross_exposure),
        "--confidence-target",
        str(args.risk_confidence_target),
        "--min-gross-exposure",
        str(args.risk_min_gross_exposure),
        "--transaction-cost-bps",
        str(args.risk_transaction_cost_bps),
        "--hold-buffer",
        str(args.risk_hold_buffer),
        "--max-turnover",
        str(args.risk_max_turnover),
        "--min-trade-weight",
        str(args.risk_min_trade_weight),
        "--benchmark-symbol",
        args.risk_benchmark_symbol,
    ]
    maybe_add_arg(command, "--metadata-csv", args.risk_metadata_csv)
    maybe_add_arg(command, "--sector-column", args.risk_sector_column)
    if args.risk_require_positive_label:
        command.append("--require-positive-label")
    if args.risk_sector_neutralization:
        command.append("--sector-neutralization")
    return command


def build_strategy_config(
    *,
    dataset_id: str,
    strategy_id: str,
    risk_positions_path: Path,
    risk_summary_path: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "strategy_id": f"{dataset_id}_{strategy_id}",
        "description": f"Alpaca ablation execution replay for {dataset_id} / {strategy_id}",
        "broker": "alpaca",
        "source": {
            "type": "risk_positions_csv",
            "path": str(risk_positions_path),
            "summary_path": str(risk_summary_path),
        },
        "execution": {
            "allow_fractional": args.execution_allow_fractional,
            "default_account_equity": args.initial_equity,
            "buying_power_buffer": args.execution_buying_power_buffer,
            "order_sizing_mode": args.execution_order_sizing_mode,
            "order_type": args.execution_order_type,
            "time_in_force": args.execution_time_in_force,
            "max_position_weight": args.execution_max_position_weight,
            "min_order_notional": args.execution_min_order_notional,
            "rebalance_step": args.risk_rebalance_step,
            "transaction_cost_bps": args.risk_transaction_cost_bps,
        },
    }


def build_execution_command(
    *,
    strategy_config_path: Path,
    execution_universe: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "execution" / "scripts" / "backtest_alpaca_style.py"),
        str(strategy_config_path),
        "--universe-csv",
        str(execution_universe),
        "--initial-equity",
        str(args.initial_equity),
        "--output-dir",
        str(output_dir),
    ]


def should_skip_existing(*, args: argparse.Namespace, expected_paths: list[Path]) -> bool:
    return args.skip_existing and all(path.exists() for path in expected_paths)


def failure_record(dataset_id: str, strategy_id: str, phase: str, message: str) -> dict[str, str]:
    return {
        "dataset_id": dataset_id,
        "strategy_id": strategy_id,
        "phase": phase,
        "error": message,
    }


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    rendered = []
    rendered.append("| " + " | ".join(headers) + " |")
    rendered.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        rendered.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(rendered)


def write_report(
    *,
    report_dir: Path,
    run_id: str,
    args: argparse.Namespace,
    aggregate_rows: list[dict[str, Any]],
    failures: list[dict[str, str]],
    metadata_path: Path,
) -> Path:
    success_rows = [row for row in aggregate_rows if row.get("status") == "ok"]
    ordered = sorted(aggregate_rows, key=lambda item: (item.get("status") != "ok", -float_or_zero(item.get("total_return"))))
    summary_headers = ["Dataset", "Strategy", "Status", "Total Return", "Sharpe", "Max Drawdown", "Mean Turnover"]
    summary_rows = [
        [
            row["dataset_id"],
            row["strategy_id"],
            row["status"],
            f"{float_or_zero(row.get('total_return')):.4f}" if row.get("status") == "ok" else "",
            f"{float_or_zero(row.get('sharpe')):.4f}" if row.get("status") == "ok" else "",
            f"{float_or_zero(row.get('max_drawdown')):.4f}" if row.get("status") == "ok" else "",
            f"{float_or_zero(row.get('mean_turnover')):.4f}" if row.get("status") == "ok" else "",
        ]
        for row in ordered
    ]
    lines = [
        f"# Alpaca Ablation Report: {run_id}",
        "",
        f"- Generated at: {iso_now()}",
        f"- Model mode: `{args.model_mode}`",
        f"- Horizon: `{args.horizon}` trading days",
        f"- Eval window: `{args.eval_start}` to `{args.eval_end}`",
        f"- Force retrain: `{args.force_retrain}`",
        f"- Skip existing: `{args.skip_existing}`",
        f"- Data origins metadata: `{metadata_path}`",
        "",
        "## Aggregate Results",
        "",
        markdown_table(summary_headers, summary_rows) if summary_rows else "_No runs completed successfully._",
        "",
        "## Best Successful Run",
        "",
    ]
    if success_rows:
        best = max(success_rows, key=lambda item: float_or_zero(item.get("total_return")))
        lines.extend(
            [
                f"- Dataset: `{best['dataset_id']}`",
                f"- Strategy: `{best['strategy_id']}`",
                f"- Total return: `{float_or_zero(best.get('total_return')):.4f}`",
                f"- Annualized return: `{float_or_zero(best.get('annualized_return')):.4f}`",
                f"- Annualized volatility: `{float_or_zero(best.get('annualized_volatility')):.4f}`",
                f"- Sharpe: `{float_or_zero(best.get('sharpe')):.4f}`",
            ]
        )
    else:
        lines.append("_No successful runs._")
    lines.extend(["", "## Failures", ""])
    if failures:
        lines.append(
            markdown_table(
                ["Dataset", "Strategy", "Phase", "Error"],
                [[item["dataset_id"], item["strategy_id"], item["phase"], item["error"].replace("\n", " ")] for item in failures],
            )
        )
    else:
        lines.append("_No failures recorded._")
    report_path = report_dir / "ablation_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a fixed 2x6 Alpaca-style ablation across base experts and an ensemble vote strategy."
    )
    parser.add_argument("--run-id", default="", help="Experiment run id. Defaults to a timestamped name.")
    parser.add_argument(
        "--force-retrain",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Retrain all 10 base models before prediction/risk/execution. Use --no-force-retrain to reuse artifacts.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a step when expected outputs already exist. Training still reruns when --force-retrain is enabled.",
    )
    parser.add_argument(
        "--a-share-dataset",
        default=first_existing_path([
            str(PROJECT_ROOT / "data" / "interim" / "akshare" / "universes" / "large_cap_50_20200101_20241231_hfq_normalized.csv")
        ]),
        help="Training dataset for d1_a_share_only.",
    )
    parser.add_argument(
        "--a-share-plus-us-dataset",
        default=first_existing_path([
            str(PROJECT_ROOT / "data" / "interim" / "experiments" / "ablation" / "a_share_plus_us_full_19900101_20260322_hfq_normalized.csv"),
            str(PROJECT_ROOT / "data" / "interim" / "experiments" / "ablation" / "a_share_plus_us_full_19900101_20260323_hfq_normalized.csv"),
        ]),
        help="Training dataset for d2_a_share_plus_us.",
    )
    parser.add_argument(
        "--eval-universe",
        default=first_existing_path([
            str(PROJECT_ROOT / "data" / "interim" / "alpaca" / "universes" / "us_large_cap_30_latest_hfq_normalized.csv"),
            str(PROJECT_ROOT / "data" / "interim" / "alpaca" / "universes" / "us_large_cap_30_19900101_20260322_hfq_normalized.csv"),
        ]),
        help="Evaluation universe used for prediction.",
    )
    parser.add_argument("--execution-universe", default="", help="Optional execution backtest universe. Defaults to --eval-universe.")
    parser.add_argument("--eval-start", default="2024-01-01", help="Inclusive evaluation start date.")
    parser.add_argument("--eval-end", default=datetime.now().astimezone().date().isoformat(), help="Inclusive evaluation end date.")
    parser.add_argument("--model-mode", default="regression", help="Expert training mode.")
    parser.add_argument("--horizon", type=int, default=5, help="Forecast horizon in trading days.")
    parser.add_argument("--train-ratio", type=float, default=0.7, help="Training split ratio.")
    parser.add_argument("--valid-ratio", type=float, default=0.15, help="Validation split ratio.")
    parser.add_argument("--seed", type=int, default=42, help="Seed used where the expert supports one.")
    parser.add_argument("--torch-device", default="", help="Optional torch device override for LSTM/Transformer.")
    parser.add_argument("--initial-equity", type=float, default=100000.0, help="Backtest starting equity.")
    parser.add_argument("--execution-buying-power-buffer", type=float, default=1.0, help="Execution buying_power_buffer for temp strategy configs.")
    parser.add_argument("--execution-order-sizing-mode", default="hybrid", help="Execution order sizing mode.")
    parser.add_argument("--execution-order-type", default="market", help="Execution order type.")
    parser.add_argument("--execution-time-in-force", default="day", help="Execution time in force.")
    parser.add_argument(
        "--execution-allow-fractional",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether execution backtests can trade fractional quantities.",
    )
    parser.add_argument("--execution-max-position-weight", type=float, default=0.35, help="Execution-side max position weight.")
    parser.add_argument("--execution-min-order-notional", type=float, default=0.0, help="Execution-side minimum order notional.")
    parser.add_argument(
        "--risk-metadata-csv",
        default=first_existing_path([
            str(PROJECT_ROOT / "data" / "interim" / "alpaca" / "universes" / "us_large_cap_30_metadata.csv"),
            "",
        ]),
        help="Optional metadata CSV passed to the white-box risk pipeline.",
    )
    parser.add_argument("--risk-rebalance-step", type=int, default=1, help="White-box rebalance step.")
    parser.add_argument("--risk-top-k", type=int, default=5, help="White-box top-k.")
    parser.add_argument("--risk-min-score", type=float, default=0.0, help="White-box min score.")
    parser.add_argument("--risk-min-confidence", type=float, default=0.7, help="White-box min confidence.")
    parser.add_argument("--risk-require-positive-label", action="store_true", help="Require pred_label == 1.")
    parser.add_argument("--risk-min-close", type=float, default=5.0, help="White-box min close.")
    parser.add_argument("--risk-max-close", type=float, default=0.0, help="White-box max close.")
    parser.add_argument("--risk-min-amount", type=float, default=100000000.0, help="White-box min amount.")
    parser.add_argument("--risk-min-turnover", type=float, default=0.0, help="White-box min turnover.")
    parser.add_argument("--risk-min-volume", type=float, default=0.0, help="White-box min volume.")
    parser.add_argument("--risk-min-median-dollar-volume-20", type=float, default=0.0, help="White-box min 20-day median dollar volume.")
    parser.add_argument("--risk-max-vol-20", type=float, default=0.0, help="White-box max 20-day volatility.")
    parser.add_argument("--risk-group-column", default="industry_group", help="White-box primary group column.")
    parser.add_argument("--risk-max-per-group", type=int, default=1, help="White-box max per primary group.")
    parser.add_argument("--risk-secondary-group-column", default="amount_bucket", help="White-box secondary group column.")
    parser.add_argument("--risk-secondary-max-per-group", type=int, default=2, help="White-box max per secondary group.")
    parser.add_argument("--risk-weighting", default="score_confidence", help="White-box weighting scheme.")
    parser.add_argument("--risk-max-position-weight", type=float, default=0.35, help="White-box max position weight.")
    parser.add_argument("--risk-max-gross-exposure", type=float, default=0.85, help="White-box max gross exposure.")
    parser.add_argument("--risk-confidence-target", type=float, default=0.90, help="White-box confidence target.")
    parser.add_argument("--risk-min-gross-exposure", type=float, default=0.55, help="White-box min gross exposure.")
    parser.add_argument("--risk-transaction-cost-bps", type=float, default=10.0, help="White-box transaction cost bps.")
    parser.add_argument("--risk-hold-buffer", type=float, default=0.0, help="White-box hold buffer.")
    parser.add_argument("--risk-max-turnover", type=float, default=0.0, help="White-box max turnover.")
    parser.add_argument("--risk-min-trade-weight", type=float, default=0.0, help="White-box min trade weight.")
    parser.add_argument("--risk-sector-neutralization", action="store_true", help="Enable white-box sector-neutralization.")
    parser.add_argument("--risk-sector-column", default="", help="White-box sector column.")
    parser.add_argument("--risk-benchmark-symbol", default="SPY", help="White-box benchmark symbol.")
    parser.add_argument(
        "--source-manifest-path",
        default=first_existing_path([
            str(PROJECT_ROOT / "data" / "interim" / "alpaca" / "universes" / "us_large_cap_30_latest_hfq_manifest.json"),
            "",
        ]),
        help="Optional source manifest archived in experiment metadata.",
    )
    parser.add_argument("--source-fetched-at", default="", help="Optional fetch timestamp recorded in metadata.")
    parser.add_argument("--a-share-symbols-file", default=str(PROJECT_ROOT / "configs" / "stock_universe_large_cap_50.txt"), help="A-share symbols file recorded in metadata.")
    parser.add_argument("--us-symbols-file", default=str(PROJECT_ROOT / "configs" / "stock_universe_us_large_cap_30.txt"), help="US symbols file recorded in metadata.")
    parser.add_argument("--a-share-price-provider-label", default="akshare", help="A-share price provider label.")
    parser.add_argument("--a-share-price-source-label", default="ak.stock_zh_a_hist", help="A-share price source label.")
    parser.add_argument("--a-share-price-origin-url", default="", help="A-share price origin URL or label.")
    parser.add_argument("--a-share-metadata-provider-label", default="akshare", help="A-share metadata provider label.")
    parser.add_argument("--a-share-metadata-source-label", default="ak.stock_industry_change_cninfo", help="A-share metadata source label.")
    parser.add_argument("--a-share-metadata-origin-url", default="", help="A-share metadata origin URL or label.")
    parser.add_argument("--us-price-provider-label", default="alpaca", help="US price provider label.")
    parser.add_argument("--us-price-source-label", default="GET /v2/stocks/bars", help="US price source label.")
    parser.add_argument("--us-price-origin-url", default="https://data.alpaca.markets/v2/stocks/bars", help="US price origin URL.")
    parser.add_argument("--us-metadata-provider-label", default="wikipedia_sp500", help="US metadata provider label.")
    parser.add_argument("--us-metadata-source-label", default="List_of_S%26P_500_companies", help="US metadata source label.")
    parser.add_argument("--us-metadata-origin-url", default="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", help="US metadata origin URL.")
    parser.add_argument("--us-alpaca-feed", default="iex", help="US Alpaca feed label recorded in metadata.")
    parser.add_argument("--us-alpaca-adjustment", default="raw", help="US Alpaca adjustment label recorded in metadata.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = args.run_id.strip() or build_default_run_id()
    experiment_dir = PROJECT_ROOT / "artifacts" / "experiments" / run_id
    report_dir = experiment_dir / "report"
    logs_dir = experiment_dir / "logs"
    report_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    datasets = dataset_specs(args)
    eval_universe = ensure_file(resolve_path(args.eval_universe), label="eval universe CSV")
    execution_universe = ensure_file(resolve_path(args.execution_universe), label="execution universe CSV") if args.execution_universe else eval_universe
    for dataset_id in DATASET_IDS:
        ensure_file(datasets[dataset_id]["train_csv"], label=f"{dataset_id} training dataset")
    if args.risk_metadata_csv:
        ensure_file(resolve_path(args.risk_metadata_csv), label="risk metadata CSV")
    if args.source_manifest_path:
        ensure_file(resolve_path(args.source_manifest_path), label="source manifest")

    metadata_path = experiment_dir / "data_origins.json"
    write_json(
        metadata_path,
        build_data_origins_payload(
            args,
            run_id=run_id,
            experiment_dir=experiment_dir,
            datasets=datasets,
            eval_universe=eval_universe,
            execution_universe=execution_universe,
        ),
    )

    training_map: dict[tuple[str, str], TrainingArtifact] = {}
    prediction_map: dict[tuple[str, str], Path] = {}
    aggregate_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    print(f"[INFO] Run id: {run_id}")
    print(f"[INFO] Experiment dir: {experiment_dir}")
    print("[INFO] Phase 1/4: train 10 base models")
    for dataset_id in DATASET_IDS:
        dataset_dir = experiment_dir / "train" / dataset_id
        input_csv = datasets[dataset_id]["train_csv"]
        for expert in BASE_EXPERTS:
            output_dir = dataset_dir / expert
            log_path = logs_dir / "train" / dataset_id / f"{expert}.log"
            metrics_path = output_dir / "metrics.json"
            expected_paths = [metrics_path, expected_model_path(output_dir, expert)]
            try:
                if args.force_retrain:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    run_subprocess(build_train_command(expert=expert, input_csv=input_csv, output_dir=output_dir, args=args), log_path=log_path)
                elif should_skip_existing(args=args, expected_paths=expected_paths):
                    pass
                elif not train_artifacts_exist(output_dir, expert):
                    output_dir.mkdir(parents=True, exist_ok=True)
                    run_subprocess(build_train_command(expert=expert, input_csv=input_csv, output_dir=output_dir, args=args), log_path=log_path)
                training_map[(dataset_id, expert)] = TrainingArtifact(
                    dataset_id=dataset_id,
                    expert=expert,
                    output_dir=output_dir,
                    model_path=load_model_path(output_dir, expert),
                    metrics_path=ensure_file(metrics_path, label=f"{dataset_id}/{expert} metrics"),
                )
                print(f"[OK] trained {dataset_id}/{expert}")
            except Exception as exc:
                message = str(exc)
                failures.append(failure_record(dataset_id, expert, "train", message))
                print(f"[ERROR] train failed for {dataset_id}/{expert}: {message}")

    print("[INFO] Phase 2/4: predict base experts, then ensemble vote")
    for dataset_id in DATASET_IDS:
        for expert in BASE_EXPERTS:
            training = training_map.get((dataset_id, expert))
            if training is None:
                continue
            output_dir = experiment_dir / "predict" / dataset_id / expert
            log_path = logs_dir / "predict" / dataset_id / f"{expert}.log"
            predictions_path = prediction_artifact_path(output_dir)
            try:
                if not should_skip_existing(args=args, expected_paths=[predictions_path]):
                    output_dir.mkdir(parents=True, exist_ok=True)
                    run_subprocess(
                        build_predict_command(
                            expert=expert,
                            input_csv=eval_universe,
                            model_path=training.model_path,
                            metrics_path=training.metrics_path,
                            output_dir=output_dir,
                            args=args,
                        ),
                        log_path=log_path,
                    )
                prediction_map[(dataset_id, expert)] = ensure_file(predictions_path, label=f"{dataset_id}/{expert} prediction CSV")
                print(f"[OK] predicted {dataset_id}/{expert}")
            except Exception as exc:
                message = str(exc)
                failures.append(failure_record(dataset_id, expert, "predict", message))
                print(f"[ERROR] predict failed for {dataset_id}/{expert}: {message}")

        ensemble_predictions = [prediction_map.get((dataset_id, expert)) for expert in BASE_EXPERTS]
        if any(path is None for path in ensemble_predictions):
            missing = [expert for expert in BASE_EXPERTS if prediction_map.get((dataset_id, expert)) is None]
            message = f"Missing base prediction CSVs for ensemble: {', '.join(missing)}"
            failures.append(failure_record(dataset_id, "ensemble_vote", "predict", message))
            print(f"[ERROR] predict failed for {dataset_id}/ensemble_vote: {message}")
            continue
        ensemble_output_dir = experiment_dir / "predict" / dataset_id / "ensemble_vote"
        ensemble_log = logs_dir / "predict" / dataset_id / "ensemble_vote.log"
        ensemble_prediction_path = prediction_artifact_path(ensemble_output_dir)
        try:
            if not should_skip_existing(args=args, expected_paths=[ensemble_prediction_path]):
                ensemble_output_dir.mkdir(parents=True, exist_ok=True)
                run_subprocess(
                    build_ensemble_command(prediction_csvs=[path for path in ensemble_predictions if path is not None], output_dir=ensemble_output_dir),
                    log_path=ensemble_log,
                )
            prediction_map[(dataset_id, "ensemble_vote")] = ensure_file(ensemble_prediction_path, label=f"{dataset_id}/ensemble_vote prediction CSV")
            print(f"[OK] predicted {dataset_id}/ensemble_vote")
        except Exception as exc:
            message = str(exc)
            failures.append(failure_record(dataset_id, "ensemble_vote", "predict", message))
            print(f"[ERROR] predict failed for {dataset_id}/ensemble_vote: {message}")

    print("[INFO] Phase 3/4: white-box risk and Alpaca-style execution")
    for dataset_id in DATASET_IDS:
        for strategy_id in ALL_STRATEGIES:
            predictions_csv = prediction_map.get((dataset_id, strategy_id))
            if predictions_csv is None:
                aggregate_rows.append({"dataset_id": dataset_id, "strategy_id": strategy_id, "status": "failed", "primary_summary_path": ""})
                continue

            risk_output_dir = experiment_dir / "risk" / dataset_id / strategy_id
            risk_logs = logs_dir / "risk" / dataset_id / f"{strategy_id}.log"
            risk_paths = risk_artifact_paths(risk_output_dir)
            try:
                if not should_skip_existing(args=args, expected_paths=[risk_paths["positions"], risk_paths["periods"], risk_paths["summary"]]):
                    risk_output_dir.mkdir(parents=True, exist_ok=True)
                    run_subprocess(
                        build_risk_command(
                            predictions_csv=predictions_csv,
                            output_dir=risk_output_dir,
                            strategy_name=f"{dataset_id}_{strategy_id}",
                            args=args,
                        ),
                        log_path=risk_logs,
                    )
                risk_positions_path = ensure_file(risk_paths["positions"], label=f"{dataset_id}/{strategy_id} risk positions")
                risk_summary_path = ensure_file(risk_paths["summary"], label=f"{dataset_id}/{strategy_id} risk summary")
            except Exception as exc:
                message = str(exc)
                failures.append(failure_record(dataset_id, strategy_id, "risk", message))
                aggregate_rows.append({"dataset_id": dataset_id, "strategy_id": strategy_id, "status": "failed", "primary_summary_path": ""})
                print(f"[ERROR] risk failed for {dataset_id}/{strategy_id}: {message}")
                continue

            execution_output_dir = experiment_dir / "execution" / dataset_id / strategy_id
            execution_logs = logs_dir / "execution" / dataset_id / f"{strategy_id}.log"
            execution_paths = execution_artifact_paths(execution_output_dir)
            strategy_config_path = execution_output_dir / "strategy_config.json"
            try:
                write_json(
                    strategy_config_path,
                    build_strategy_config(
                        dataset_id=dataset_id,
                        strategy_id=strategy_id,
                        risk_positions_path=risk_positions_path,
                        risk_summary_path=risk_summary_path,
                        args=args,
                    ),
                )
                if not should_skip_existing(args=args, expected_paths=[execution_paths["periods"], execution_paths["summary"]]):
                    execution_output_dir.mkdir(parents=True, exist_ok=True)
                    run_subprocess(
                        build_execution_command(
                            strategy_config_path=strategy_config_path,
                            execution_universe=execution_universe,
                            output_dir=execution_output_dir,
                            args=args,
                        ),
                        log_path=execution_logs,
                    )
                primary_summary = compute_primary_summary(
                    execution_summary_path=ensure_file(execution_paths["summary"], label=f"{dataset_id}/{strategy_id} execution summary"),
                    risk_summary_path=risk_summary_path,
                    execution_periods_path=ensure_file(execution_paths["periods"], label=f"{dataset_id}/{strategy_id} execution periods"),
                    rebalance_step=args.risk_rebalance_step,
                )
                write_json(execution_paths["primary"], primary_summary)
                aggregate_rows.append(
                    {
                        "dataset_id": dataset_id,
                        "strategy_id": strategy_id,
                        "status": "ok",
                        **primary_summary,
                        "prediction_csv": str(predictions_csv),
                        "risk_summary_path": str(risk_summary_path),
                        "execution_summary_path": str(execution_paths["summary"]),
                        "primary_summary_path": str(execution_paths["primary"]),
                    }
                )
                print(f"[OK] executed {dataset_id}/{strategy_id}")
            except Exception as exc:
                message = str(exc)
                failures.append(failure_record(dataset_id, strategy_id, "execution", message))
                aggregate_rows.append({"dataset_id": dataset_id, "strategy_id": strategy_id, "status": "failed", "primary_summary_path": ""})
                print(f"[ERROR] execution failed for {dataset_id}/{strategy_id}: {message}")

    print("[INFO] Phase 4/4: aggregate reports")
    aggregate_df = pd.DataFrame(aggregate_rows)
    if not aggregate_df.empty:
        desired_columns = ["dataset_id", "strategy_id", "status", *PRIMARY_SUMMARY_KEYS, "primary_summary_path"]
        extra_columns = [column for column in aggregate_df.columns if column not in desired_columns]
        aggregate_df = aggregate_df[[column for column in desired_columns if column in aggregate_df.columns] + extra_columns]
    aggregate_csv_path = report_dir / "aggregate_primary_summaries.csv"
    aggregate_json_path = report_dir / "aggregate_primary_summaries.json"
    aggregate_df.to_csv(aggregate_csv_path, index=False, encoding="utf-8")
    write_json(
        aggregate_json_path,
        {
            "run_id": run_id,
            "generated_at": iso_now(),
            "results": aggregate_rows,
            "failures": failures,
            "metadata_path": str(metadata_path),
        },
    )
    report_path = write_report(
        report_dir=report_dir,
        run_id=run_id,
        args=args,
        aggregate_rows=aggregate_rows,
        failures=failures,
        metadata_path=metadata_path,
    )

    print(f"[OK] Data origins metadata: {metadata_path}")
    print(f"[OK] Aggregate CSV: {aggregate_csv_path}")
    print(f"[OK] Aggregate JSON: {aggregate_json_path}")
    print(f"[OK] Markdown report: {report_path}")
    if failures:
        print(f"[WARN] Completed with {len(failures)} recorded failures.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
