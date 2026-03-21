from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from execution.common.strategy_runtime import parse_session_date
from stockmachine.apps import run_multi_expert_paper as runner
from stockmachine.state.ledger import LocalLedger
from stockmachine.state.models import OrderRecord, RunManifestRecord, RunRecord


def test_managed_paper_dry_run_records_ledger_and_state(monkeypatch, strategy_bundle_factory, tmp_path: Path) -> None:
    bundle = strategy_bundle_factory(tmp_path)
    runtime_root = tmp_path / "runtime"
    latest_root = tmp_path / "latest"
    state_root = tmp_path / "state"

    def fake_write_latest_state(strategy_id: str, payload: dict) -> dict[str, str]:
        state_dir = state_root / strategy_id
        state_dir.mkdir(parents=True, exist_ok=True)
        latest_state_path = state_dir / "latest_state.json"
        latest_state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (state_dir / "run_journal.csv").write_text("strategy_id\n", encoding="utf-8")
        (state_dir / "run_journal.jsonl").write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        return {
            "state_dir": str(state_dir),
            "latest_state_path": str(latest_state_path),
            "run_journal_csv_path": str(state_dir / "run_journal.csv"),
            "run_journal_jsonl_path": str(state_dir / "run_journal.jsonl"),
        }

    def fake_write_order_journal(strategy_id: str, rows: list[dict]) -> str:
        state_dir = state_root / strategy_id
        state_dir.mkdir(parents=True, exist_ok=True)
        journal_path = state_dir / "order_journal.csv"
        if rows:
            import pandas as pd

            pd.DataFrame(rows).to_csv(journal_path, index=False, encoding="utf-8")
        else:
            journal_path.write_text("", encoding="utf-8")
        return str(journal_path)

    def fake_sync_latest_run(strategy_id: str, run_dir: Path) -> Path:
        latest_dir = latest_root / strategy_id
        latest_dir.mkdir(parents=True, exist_ok=True)
        for name in ("execution_plan.json", "target_positions.csv", "order_intents.csv", "run_summary.json"):
            source = run_dir / name
            if source.exists():
                shutil.copy2(source, latest_dir / name)
        return latest_dir

    monkeypatch.setattr(runner, "write_latest_state", fake_write_latest_state)
    monkeypatch.setattr(runner, "write_order_journal", fake_write_order_journal)
    monkeypatch.setattr(runner, "sync_latest_run", fake_sync_latest_run)

    result = runner.run_strategy(
        bundle["strategy_config"],
        session_date_override="2026-03-21",
        submit=False,
        account_equity_override=100000.0,
        current_positions_csv=str(bundle["current_positions_csv"]),
        output_dir=str(runtime_root),
        ledger_path=str(tmp_path / "paper_ledger.sqlite3"),
        skip_session_guard=False,
    )

    assert result.summary["strategy_id"] == str(bundle["strategy_id"])
    assert result.summary["order_count"] == 3
    assert result.summary["submitted_count"] == 0
    assert result.summary["session_guard"]["allowed"] is True
    assert result.report["status"] == "success"

    plan_path = Path(result.summary["plan_json_path"])
    assert plan_path.exists()
    assert (state_root / str(bundle["strategy_id"]) / "latest_state.json").exists()

    with LocalLedger(tmp_path / "paper_ledger.sqlite3") as ledger:
        ledger.initialize()
        runs = ledger.list_run_manifests()
        assert len(runs) == 1
        assert runs[0].strategy_name == str(bundle["strategy_id"])
        decisions = ledger.list_order_decisions(run_id=result.summary["run_id"])
        assert len(decisions) == 3
        assert {decision.approved for decision in decisions} == {True}


def test_managed_paper_submit_requires_paper_environment(monkeypatch, strategy_bundle_factory, tmp_path: Path) -> None:
    bundle = strategy_bundle_factory(tmp_path)

    class FakeCredentials:
        base_url = "https://broker-api.sandbox.example.com"

    class FakeAccount:
        equity = 100000.0
        cash = 50000.0
        buying_power = 100000.0
        raw = {"status": "active", "buying_power": 100000.0}

    class FakeBroker:
        credentials = FakeCredentials()

        def is_paper_trading_environment(self) -> bool:
            return False

        def get_account_snapshot(self) -> FakeAccount:
            return FakeAccount()

        def list_positions(self) -> list[object]:
            return []

        def get_clock(self) -> dict[str, object]:
            return {"timestamp": "2026-03-21T14:00:00Z", "is_open": True}

        def list_orders(self, status: str | None = None):
            return []

    monkeypatch.setattr(runner, "load_alpaca_credentials", lambda prefix: {"prefix": prefix})
    monkeypatch.setattr(runner, "AlpacaBroker", lambda credentials: FakeBroker())

    try:
        runner.run_strategy(
            bundle["strategy_config"],
            session_date_override="2026-03-21",
            submit=True,
            account_equity_override=100000.0,
            current_positions_csv=str(bundle["current_positions_csv"]),
            output_dir=str(tmp_path / "runtime"),
            ledger_path=str(tmp_path / "paper_ledger.sqlite3"),
            skip_session_guard=True,
            require_paper=True,
        )
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "non-paper orders" in str(exc)

    assert raised is True
