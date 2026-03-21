from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from execution.managed.apps import paper_ops
from execution.managed.state.ledger import LocalLedger
from execution.managed.state.models import OrderRecord, RunManifestRecord, RunRecord


@dataclass(slots=True)
class FakeHealthcheck:
    healthy: bool
    reasons: tuple[str, ...]
    latest_state: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "healthy": self.healthy,
            "reasons": list(self.reasons),
            "latest_state": self.latest_state,
        }


def test_latest_run_uses_state_payload_and_json_safe(monkeypatch, strategy_bundle_factory, tmp_path: Path) -> None:
    bundle = strategy_bundle_factory(tmp_path)
    ledger_path = tmp_path / "paper_ledger.sqlite3"
    statuses_path = tmp_path / "submitted_order_statuses.json"
    statuses_path.write_text(
        json.dumps(
            [
                {"id": "order-1", "symbol": "AAA", "status": "new"},
                {"id": "order-2", "symbol": "BBB", "status": "filled"},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state_payload = {
        "strategy_id": str(bundle["strategy_id"]),
        "rebalance_date": "2026-03-21",
        "submitted_order_statuses_path": str(statuses_path),
        "run_dir": str(tmp_path / "runtime"),
    }
    monkeypatch.setattr(
        paper_ops,
        "build_paper_daily_healthcheck",
        lambda strategy_id: FakeHealthcheck(healthy=False, reasons=("missing_latest_state",), latest_state=state_payload),
    )

    with LocalLedger(ledger_path) as ledger:
        ledger.initialize()
        run_id = "run-1"
        ledger.record_run(
            RunRecord(
                run_id=run_id,
                strategy_name=str(bundle["strategy_id"]),
                market="US",
                created_at_utc=datetime.now(timezone.utc),
                status="finished",
                meta={"source": "test"},
            )
        )
        ledger.record_run_manifest(
            RunManifestRecord(
                run_id=run_id,
                session_date=datetime.fromisoformat("2026-03-21T00:00:00").date(),
                strategy_name=str(bundle["strategy_id"]),
                model_name="multi_expert",
                generated_at_utc=datetime.now(timezone.utc),
                client_order_id_prefix="smk",
                dry_run=True,
                data_snapshot={"source": "test"},
                risk_policy={"source": "test"},
                execution_policy={"source": "test"},
                meta={"source": "test"},
            )
        )
        ledger.upsert_order(
            OrderRecord(
                order_id="order-1",
                run_id=run_id,
                session_date=datetime.fromisoformat("2026-03-21T00:00:00").date(),
                client_order_id="client-1",
                symbol="AAA",
                side="buy",
                quantity=1.0,
                order_type="market",
                limit_price=None,
                status="new",
                filled_quantity=0.0,
                avg_fill_price=None,
                submitted_at_utc=datetime.now(timezone.utc),
                updated_at_utc=datetime.now(timezone.utc),
                broker_payload={"status": "new"},
            )
        )

    payload = paper_ops.dispatch_command(
        argparse.Namespace(
            strategy_config=str(bundle["strategy_config"]),
            command="latest-run",
            ledger_path=str(ledger_path),
        )
    )

    assert payload["run_id"] == run_id
    assert isinstance(payload["run"], dict)
    assert isinstance(payload["manifest"], dict)
    assert payload["latest_state"] == state_payload
    assert any(alert["code"] == "open_orders_lingering" for alert in payload["alerts"])


def test_run_summary_includes_report_and_latest_state(monkeypatch, strategy_bundle_factory, tmp_path: Path) -> None:
    bundle = strategy_bundle_factory(tmp_path)
    ledger_path = tmp_path / "paper_ledger.sqlite3"
    state_payload = {
        "strategy_id": str(bundle["strategy_id"]),
        "rebalance_date": "2026-03-21",
        "submitted_order_statuses_path": str(tmp_path / "submitted_order_statuses.json"),
    }
    monkeypatch.setattr(
        paper_ops,
        "build_paper_daily_healthcheck",
        lambda strategy_id: FakeHealthcheck(healthy=True, reasons=(), latest_state=state_payload),
    )

    with LocalLedger(ledger_path) as ledger:
        ledger.initialize()
        run_id = "run-2"
        ledger.record_run(
            RunRecord(
                run_id=run_id,
                strategy_name=str(bundle["strategy_id"]),
                market="US",
                created_at_utc=datetime.now(timezone.utc),
                status="finished",
                meta={},
            )
        )

    payload = paper_ops.dispatch_command(
        argparse.Namespace(
            strategy_config=str(bundle["strategy_config"]),
            command="run-summary",
            run_id=run_id,
            ledger_path=str(ledger_path),
        )
    )

    assert payload["run_id"] == run_id
    assert payload["report"]["run_id"] == run_id
    assert payload["latest_state"] == state_payload

