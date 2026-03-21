#!/usr/bin/env python3
"""Generate or submit a paper-trading execution plan for one strategy config."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from execution.alpaca.client import AlpacaBroker, load_alpaca_credentials
from execution.alpaca.account_monitor import save_account_snapshot
from execution.alpaca.order_router import submit_execution_plan
from execution.common.execution_models import ExecutionPlan, PositionSnapshot, TargetPosition
from execution.common.order_safety import validate_execution_plan
from execution.common.reconciliation import build_order_intents, normalize_current_weights
from execution.common.state_store import write_latest_state, write_order_journal
from execution.common.strategy_runtime import (
    load_local_positions,
    load_strategy_config,
    load_target_positions,
    normalized_buffer,
    runtime_dir,
    save_plan,
    sync_latest_run,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or submit a paper-trading execution plan from a strategy config."
    )
    parser.add_argument("strategy_config", help="Path to a strategy JSON config.")
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit orders to Alpaca instead of running a dry plan only.",
    )
    parser.add_argument(
        "--account-equity",
        type=float,
        default=0.0,
        help="Override account equity used for dry-run planning.",
    )
    parser.add_argument(
        "--current-positions-csv",
        default="",
        help="Optional local CSV of current positions for dry-run reconciliation.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional runtime output directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_strategy_config(args.strategy_config)
    strategy_id = str(config["strategy_id"])
    broker_name = str(config.get("broker", "alpaca"))
    execution_config = dict(config.get("execution", {}))
    source = dict(config.get("source", {}))
    if source.get("type") != "risk_positions_csv":
        raise ValueError("Only risk_positions_csv source is supported right now.")

    targets = load_target_positions(
        str(source["path"]),
        rebalance_selection=str(execution_config.get("rebalance_selection", "latest")),
        actions_path=source.get("actions_path", ""),
    )

    if args.submit:
        credentials = load_alpaca_credentials(str(config["paper_env_prefix"]))
        broker = AlpacaBroker(credentials)
        account = broker.get_account_snapshot()
        current_positions = normalize_current_weights(
            broker.list_positions(),
            account_equity=account.equity,
        )
        account_equity = account.equity
        account_buying_power = account.buying_power
    else:
        broker = None
        account_equity = (
            args.account_equity
            if args.account_equity > 0
            else float(execution_config.get("default_account_equity", 100000.0))
        )
        account_buying_power = account_equity
        current_positions = normalize_current_weights(
            load_local_positions(args.current_positions_csv) if args.current_positions_csv else [],
            account_equity=account_equity,
        )
    buying_power_buffer = normalized_buffer(execution_config.get("buying_power_buffer", 1.0))
    planning_equity = account_equity * buying_power_buffer

    order_intents = build_order_intents(
        targets,
        current_positions,
        account_equity=account_equity,
        planning_equity=planning_equity,
        allow_fractional=bool(execution_config.get("allow_fractional", True)),
        order_sizing_mode=str(execution_config.get("order_sizing_mode", "notional")),
        order_type=str(execution_config.get("order_type", "market")),
        time_in_force=str(execution_config.get("time_in_force", "day")),
    )
    plan = ExecutionPlan(
        strategy_id=strategy_id,
        broker=broker_name,
        rebalance_date=targets[0].rebalance_date if targets else "",
        generated_at=datetime.now(timezone.utc).isoformat(),
        account_equity=account_equity,
        planning_equity=planning_equity,
        account_buying_power=account_buying_power,
        current_positions=current_positions,
        target_positions=targets,
        order_intents=order_intents,
        notes=[],
    )
    if buying_power_buffer < 1.0:
        plan.notes.append(
            f"Apply buying_power_buffer={buying_power_buffer:.4f}; planning_equity={planning_equity:.2f}."
        )
    plan = validate_execution_plan(
        plan,
        max_position_weight=float(execution_config.get("max_position_weight", 1.0)),
        min_order_notional=float(execution_config.get("min_order_notional", 0.0)),
    )

    out_dir = runtime_dir(strategy_id, args.output_dir)
    saved = save_plan(out_dir, plan)

    submitted_orders = []
    attempt_logs: list[dict[str, object]] = []
    order_statuses: list[dict[str, object]] = []
    snapshot_paths: dict[str, str] = {}
    if args.submit and broker is not None:
        snapshot_paths.update(save_account_snapshot(broker, out_dir, prefix="pre"))
        submission_result = submit_execution_plan(
            broker,
            plan,
            cancel_open_orders_first=bool(execution_config.get("cancel_open_orders_first", True)),
            buy_retry_shrink_ratio=float(execution_config.get("buy_retry_shrink_ratio", 0.97)),
            max_buy_retries=int(execution_config.get("max_buy_retries", 1)),
            refresh_status_after_submit=bool(execution_config.get("refresh_status_after_submit", True)),
        )
        submitted_orders = submission_result["submitted_orders"]
        attempt_logs = submission_result["attempt_logs"]
        order_statuses = submission_result["order_statuses"]
        (out_dir / "submitted_orders.json").write_text(
            json.dumps([item.to_dict() for item in submitted_orders], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out_dir / "submission_attempts.json").write_text(
            json.dumps(attempt_logs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out_dir / "submitted_order_statuses.json").write_text(
            json.dumps(order_statuses, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        snapshot_paths.update(save_account_snapshot(broker, out_dir, prefix="post"))

    summary = {
        "strategy_id": strategy_id,
        "broker": broker_name,
        "rebalance_date": plan.rebalance_date,
        "account_equity": account_equity,
        "planning_equity": planning_equity,
        "account_buying_power": account_buying_power,
        "buying_power_buffer": buying_power_buffer,
        "target_count": len(plan.target_positions),
        "order_count": len(plan.order_intents),
        "submit_mode": bool(args.submit),
        "submitted_count": len(submitted_orders),
        "attempt_count": len(attempt_logs),
        "status_snapshot_count": len(order_statuses),
        "plan_json_path": saved["plan_json_path"],
        "targets_csv_path": saved["targets_csv_path"],
        "intents_csv_path": saved["intents_csv_path"],
        "notes": plan.notes,
        "source_summary_path": str(source.get("summary_path", "")),
        "run_dir": str(out_dir),
        "submitted_orders_path": str(out_dir / "submitted_orders.json") if submitted_orders else "",
        "submission_attempts_path": str(out_dir / "submission_attempts.json") if attempt_logs else "",
        "submitted_order_statuses_path": (
            str(out_dir / "submitted_order_statuses.json") if order_statuses else ""
        ),
        **snapshot_paths,
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_runtime_path = sync_latest_run(strategy_id, out_dir)

    order_rows: list[dict[str, object]] = []
    status_by_order_id = {
        str(item.get("id", "")): str(item.get("status", ""))
        for item in order_statuses
        if str(item.get("id", ""))
    }
    source_rows = attempt_logs if attempt_logs else [item.to_dict() for item in submitted_orders]
    for item in source_rows:
        row = dict(item)
        order_id = str(row.get("order_id", ""))
        if order_id:
            row["latest_status"] = status_by_order_id.get(order_id, row.get("status", ""))
        row["strategy_id"] = strategy_id
        row["rebalance_date"] = plan.rebalance_date
        row["generated_at"] = plan.generated_at
        row["run_dir"] = str(out_dir)
        order_rows.append(row)

    state_paths = write_latest_state(
        strategy_id,
        {
            **summary,
            "latest_runtime_dir": str(latest_runtime_path),
        },
    )
    order_journal_path = write_order_journal(strategy_id, order_rows)

    print(f"[OK] Execution plan: {saved['plan_json_path']}")
    print(f"[OK] Target positions: {saved['targets_csv_path']}")
    print(f"[OK] Order intents: {saved['intents_csv_path']}")
    print(f"[OK] Latest state: {state_paths['latest_state_path']}")
    print(f"[OK] Order journal: {order_journal_path}")
    print(f"[INFO] Rebalance date: {plan.rebalance_date}")
    print(f"[INFO] Order count: {len(plan.order_intents)}")
    if args.submit:
        print(f"[INFO] Submitted orders: {len(submitted_orders)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
