from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from execution.managed.live.reconciler import PollingOrderReconciler
from execution.managed.state.ledger import LocalLedger
from execution.managed.state.models import OrderDecisionRecord, RunRecord


def test_reconciler_attaches_broker_orders_to_run_via_order_decision(tmp_path: Path) -> None:
    ledger_path = tmp_path / "paper_ledger.sqlite3"
    run_id = "run-123"
    client_order_id = "qsf-20260320-ORCL-BUY-0001-run123"
    decision_time = datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc)

    with LocalLedger(ledger_path) as ledger:
        ledger.initialize()
        ledger.record_run(
            RunRecord(
                run_id=run_id,
                strategy_name="demo",
                market="US",
                created_at_utc=decision_time,
                status="running",
                meta={},
            )
        )
        ledger.record_order_decision(
            OrderDecisionRecord(
                decision_id="decision-1",
                run_id=run_id,
                session_date=date(2026, 3, 20),
                client_order_id=client_order_id,
                symbol="ORCL",
                side="BUY",
                decision_type="notional",
                decision_price=150.0,
                estimated_notional=5000.0,
                approved=True,
                reason="approved",
                decision_at_utc=decision_time,
                meta={},
            )
        )

        reconciler = PollingOrderReconciler(ledger)
        reconciler.reconcile_orders(
            [
                {
                    "id": "broker-order-1",
                    "client_order_id": client_order_id,
                    "symbol": "ORCL",
                    "side": "buy",
                    "status": "accepted",
                    "qty": "10",
                    "filled_qty": "0",
                    "submitted_at": "2026-03-21T12:00:00Z",
                    "updated_at": "2026-03-21T12:01:00Z",
                    "type": "market",
                }
            ]
        )

        open_orders = ledger.list_open_orders(run_id=run_id)
        assert len(open_orders) == 1
        assert open_orders[0].order_id == "broker-order-1"
        assert open_orders[0].client_order_id == client_order_id
