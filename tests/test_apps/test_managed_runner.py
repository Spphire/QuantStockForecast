from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from execution.managed.apps import paper_ops
from execution.managed.apps.run_multi_expert_paper import run_strategy
from execution.managed.monitoring.healthcheck import build_paper_daily_healthcheck


def _write_csv(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")


def _build_strategy_fixture(tmp_path: Path) -> tuple[Path, Path]:
    rebalance_date = date.today().isoformat()
    positions_path = tmp_path / "risk_positions.csv"
    actions_path = tmp_path / "risk_actions.csv"
    current_positions_path = tmp_path / "current_positions.csv"
    summary_path = tmp_path / "risk_summary.json"
    summary_path.write_text("{}", encoding="utf-8")

    _write_csv(
        positions_path,
        [
            {
                "rebalance_date": rebalance_date,
                "symbol": "AAPL",
                "target_weight": 0.50,
                "previous_weight": 0.20,
                "action": "add",
                "close": 100.0,
                "score": 0.9,
                "confidence": 0.8,
                "model_mode": "multi_expert",
            },
            {
                "rebalance_date": rebalance_date,
                "symbol": "MSFT",
                "target_weight": 0.25,
                "previous_weight": 0.00,
                "action": "open",
                "close": 200.0,
                "score": 0.7,
                "confidence": 0.6,
                "model_mode": "multi_expert",
            },
        ],
    )
    _write_csv(
        actions_path,
        [
            {
                "rebalance_date": rebalance_date,
                "symbol": "AAPL",
                "target_weight": 0.50,
                "previous_weight": 0.20,
                "action": "add",
                "close": 100.0,
            },
            {
                "rebalance_date": rebalance_date,
                "symbol": "MSFT",
                "target_weight": 0.25,
                "previous_weight": 0.00,
                "action": "open",
                "close": 200.0,
            },
            {
                "rebalance_date": rebalance_date,
                "symbol": "TSLA",
                "target_weight": 0.00,
                "previous_weight": 0.25,
                "action": "exit",
            },
        ],
    )
    _write_csv(
        current_positions_path,
        [
            {"symbol": "AAPL", "qty": 2.0, "market_value": 200.0, "current_price": 100.0},
            {"symbol": "TSLA", "qty": 5.0, "market_value": 250.0, "current_price": 50.0},
        ],
    )

    strategy_path = tmp_path / "strategy.json"
    strategy_path.write_text(
        json.dumps(
            {
                "strategy_id": "demo_strategy",
                "broker": "alpaca",
                "market": "US",
                "paper_env_prefix": "ALPACA_DEMO",
                "source": {
                    "type": "risk_positions_csv",
                    "path": str(positions_path),
                    "actions_path": str(actions_path),
                    "summary_path": str(summary_path),
                },
                "execution": {
                    "rebalance_selection": "latest",
                    "default_account_equity": 1000.0,
                    "allow_fractional": True,
                    "order_sizing_mode": "hybrid",
                    "buying_power_buffer": 1.0,
                    "min_order_notional": 0.0,
                    "max_position_weight": 1.0,
                    "order_type": "market",
                    "time_in_force": "day",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return strategy_path, current_positions_path


def test_managed_runner_dry_run_updates_state_and_ops(isolated_project_root, tmp_path):
    strategy_path, current_positions_path = _build_strategy_fixture(tmp_path)
    runtime_path = tmp_path / "runtime" / "demo_strategy"
    ledger_path = tmp_path / "artifacts" / "paper_ledger.sqlite3"

    result = run_strategy(
        strategy_path,
        account_equity_override=1000.0,
        current_positions_csv=str(current_positions_path),
        output_dir=str(runtime_path),
        ledger_path=str(ledger_path),
    )

    assert result.summary["strategy_id"] == "demo_strategy"
    assert result.summary["target_count"] == 3
    assert result.summary["order_count"] == 3
    assert Path(result.summary["plan_json_path"]).exists()
    assert ledger_path.exists()

    state_root = isolated_project_root / "execution" / "state"
    state_path = state_root / "demo_strategy" / "latest_state.json"
    assert state_path.exists()

    healthcheck = build_paper_daily_healthcheck(
        "demo_strategy",
        state_root=state_root,
        reference_date=date.today(),
    )
    assert healthcheck.healthy is True
    assert healthcheck.latest_state is not None

    payload = paper_ops.dispatch_command(
        argparse.Namespace(
            strategy_config=str(strategy_path),
            ledger_path=str(ledger_path),
            command="latest-run",
        )
    )
    assert payload["run_id"] == result.summary["run_id"]
    assert payload["latest_state"]["strategy_id"] == "demo_strategy"
    assert payload["alerts"] == []

