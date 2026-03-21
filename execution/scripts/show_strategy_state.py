#!/usr/bin/env python3
"""Show the latest persisted state for one execution strategy."""

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
    parser = argparse.ArgumentParser(description="Inspect the latest state for one strategy.")
    parser.add_argument("strategy_id", help="Execution strategy id.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = PROJECT_ROOT / "execution" / "state" / args.strategy_id
    latest_state_path = state_dir / "latest_state.json"
    if not latest_state_path.exists():
        print(f"[ERROR] Latest state not found: {latest_state_path}")
        return 1

    payload = json.loads(latest_state_path.read_text(encoding="utf-8"))
    print(f"[OK] Strategy: {payload.get('strategy_id', args.strategy_id)}")
    print(f"[INFO] Rebalance date: {payload.get('rebalance_date', '')}")
    print(f"[INFO] Submit mode: {payload.get('submit_mode', False)}")
    print(f"[INFO] Submitted count: {payload.get('submitted_count', 0)}")
    print(f"[INFO] Attempt count: {payload.get('attempt_count', 0)}")
    print(f"[INFO] Latest runtime dir: {payload.get('latest_runtime_dir', '')}")
    print(f"[INFO] Planning equity: {payload.get('planning_equity', 0)}")
    print(f"[INFO] Buying power buffer: {payload.get('buying_power_buffer', 1.0)}")

    order_journal_path = state_dir / "order_journal.csv"
    if order_journal_path.exists():
        journal = pd.read_csv(order_journal_path, encoding="utf-8-sig")
        print(f"[INFO] Order journal rows: {len(journal)}")
        if not journal.empty:
            latest = journal.tail(5)
            print(latest.to_string(index=False))
    else:
        print("[INFO] Order journal rows: 0")

    status_path = Path(str(payload.get("submitted_order_statuses_path", "")))
    if status_path.exists():
        statuses = json.loads(status_path.read_text(encoding="utf-8"))
        if statuses:
            latest_statuses = [
                {
                    "symbol": item.get("symbol", ""),
                    "side": item.get("side", ""),
                    "status": item.get("status", ""),
                    "qty": item.get("qty", ""),
                    "notional": item.get("notional", ""),
                    "filled_qty": item.get("filled_qty", ""),
                }
                for item in statuses[-5:]
            ]
            print("[INFO] Latest order statuses:")
            print(pd.DataFrame(latest_statuses).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
