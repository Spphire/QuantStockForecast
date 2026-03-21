from __future__ import annotations

import json
from pathlib import Path

from execution.common.execution_models import ExecutionPlan, OrderIntent, PositionSnapshot, TargetPosition
from execution.common import strategy_runtime
from execution.common.strategy_runtime import (
    available_rebalance_dates,
    load_local_positions,
    load_target_positions,
    save_plan,
    sync_latest_run,
)


def test_available_rebalance_dates_and_exit_targets(strategy_bundle_factory, tmp_path: Path) -> None:
    bundle = strategy_bundle_factory(tmp_path, rebalance_dates=("2026-03-21", "2026-03-22"))

    dates = available_rebalance_dates(bundle["source_csv"], actions_path=bundle["actions_csv"])
    assert dates == ["2026-03-21", "2026-03-22"]

    targets = load_target_positions(
        bundle["source_csv"],
        "latest",
        actions_path=bundle["actions_csv"],
    )
    assert [target.symbol for target in targets] == ["AAA", "BBB", "CCC"]
    assert targets[-1].action == "exit"
    assert targets[-1].target_weight == 0.0

    positions = load_local_positions(bundle["current_positions_csv"])
    assert [position.symbol for position in positions] == ["AAA", "BBB", "CCC"]


def test_save_plan_and_sync_latest_run(monkeypatch, strategy_bundle_factory, tmp_path: Path) -> None:
    bundle = strategy_bundle_factory(tmp_path)
    run_dir = tmp_path / "runtime"
    latest_root = tmp_path / "latest"

    monkeypatch.setattr(strategy_runtime, "latest_dir", lambda strategy_id: latest_root / strategy_id)

    plan = ExecutionPlan(
        strategy_id=str(bundle["strategy_id"]),
        broker="alpaca",
        rebalance_date="2026-03-21",
        generated_at="2026-03-22T00:00:00Z",
        account_equity=100000.0,
        planning_equity=100000.0,
        account_buying_power=100000.0,
        current_positions=[PositionSnapshot(symbol="AAA", qty=0, market_value=0, current_price=100)],
        target_positions=[
            TargetPosition(
                symbol="AAA",
                target_weight=0.5,
                previous_weight=0.1,
                action="hold",
                reference_price=100.0,
                score=0.9,
                confidence=0.8,
                rebalance_date="2026-03-21",
                metadata={"model_mode": "multi_expert"},
            )
        ],
        order_intents=[
            OrderIntent(
                symbol="AAA",
                side="buy",
                delta_notional=50000.0,
                reference_price=100.0,
                estimated_qty=500.0,
                submit_notional=50000.0,
                submit_qty=0.0,
                target_weight=0.5,
                current_weight=0.0,
                current_notional=0.0,
                target_notional=50000.0,
                reason="test order",
            )
        ],
    )

    saved_paths = save_plan(run_dir, plan)
    assert Path(saved_paths["plan_json_path"]).exists()
    assert Path(saved_paths["targets_csv_path"]).exists()
    assert Path(saved_paths["intents_csv_path"]).exists()

    latest_path = sync_latest_run(str(bundle["strategy_id"]), run_dir)
    assert latest_path == latest_root / str(bundle["strategy_id"])
    assert (latest_path / "execution_plan.json").exists()
    plan_payload = json.loads((latest_path / "execution_plan.json").read_text(encoding="utf-8"))
    assert plan_payload["strategy_id"] == str(bundle["strategy_id"])
