from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from execution.common.execution_models import SubmittedOrder
from execution.managed.apps import run_multi_expert_paper as runner


@dataclass
class _FakeCredentials:
    base_url: str = "https://paper-api.alpaca.markets"


@dataclass
class _FakeAccount:
    equity: float = 100000.0
    cash: float = 100000.0
    buying_power: float = 100000.0
    raw: dict = None

    def __post_init__(self) -> None:
        if self.raw is None:
            self.raw = {"status": "active", "buying_power": self.buying_power}


class _FakeBroker:
    def __init__(self) -> None:
        self.credentials = _FakeCredentials()

    def is_paper_trading_environment(self) -> bool:
        return True

    def get_account_snapshot(self) -> _FakeAccount:
        return _FakeAccount()

    def list_positions(self) -> list[object]:
        return []

    def get_clock(self) -> dict[str, object]:
        return {"timestamp": "2026-03-21T14:00:00Z", "is_open": False}

    def list_orders(self, status: str | None = None):
        return [
            {
                "id": "broker-open-1",
                "client_order_id": "old-order-1",
                "symbol": "AAPL",
                "side": "buy",
                "status": "new",
                "qty": "1",
                "filled_qty": "0",
                "submitted_at": "2026-03-21T13:59:00Z",
                "updated_at": "2026-03-21T13:59:00Z",
                "type": "market",
            }
        ]


def test_submit_ignores_existing_open_orders_when_cancel_first(
    monkeypatch,
    strategy_bundle_factory,
    tmp_path: Path,
) -> None:
    bundle = strategy_bundle_factory(tmp_path)
    submitted: dict[str, object] = {}

    monkeypatch.setattr(runner, "load_alpaca_credentials", lambda prefix: {"prefix": prefix})
    monkeypatch.setattr(runner, "AlpacaBroker", lambda credentials: _FakeBroker())
    monkeypatch.setattr(
        runner,
        "save_account_snapshot",
        lambda broker, run_dir, prefix="pre": {},
    )

    def fake_submit_execution_plan(broker, plan, **kwargs):
        submitted["order_count"] = len(plan.order_intents)
        submitted["cancel_open_orders_first"] = kwargs.get("cancel_open_orders_first")
        return {
            "submitted_orders": [
                SubmittedOrder(
                    order_id="submitted-1",
                    client_order_id="client-1",
                    symbol=plan.order_intents[0].symbol,
                    side=plan.order_intents[0].side,
                    status="accepted",
                )
            ],
            "attempt_logs": [
                {
                    "symbol": plan.order_intents[0].symbol,
                    "side": plan.order_intents[0].side,
                    "attempt": 1,
                    "client_order_id": "client-1",
                    "submit_as": plan.order_intents[0].submit_as,
                    "requested_notional": plan.order_intents[0].submit_notional,
                    "requested_qty": plan.order_intents[0].submit_qty,
                    "estimated_qty": plan.order_intents[0].estimated_qty,
                    "delta_notional": plan.order_intents[0].delta_notional,
                    "reference_price": plan.order_intents[0].reference_price,
                    "submitted": True,
                    "status": "accepted",
                    "order_id": "submitted-1",
                    "error_message": "",
                    "note": plan.order_intents[0].reason,
                }
            ],
            "order_statuses": [
                {"id": "submitted-1", "symbol": plan.order_intents[0].symbol, "status": "accepted"}
            ],
        }

    monkeypatch.setattr(runner, "submit_execution_plan", fake_submit_execution_plan)

    result = runner.run_strategy(
        bundle["strategy_config"],
        session_date_override="2026-03-21",
        submit=True,
        output_dir=str(tmp_path / "runtime"),
        ledger_path=str(tmp_path / "paper_ledger.sqlite3"),
        skip_session_guard=True,
        require_paper=True,
    )

    assert submitted["cancel_open_orders_first"] is True
    assert submitted["order_count"] == result.summary["order_count"]
    assert result.summary["validation"]["blocked_count"] == 0
    assert result.summary["validation"]["open_orders_considered"] == 0
    assert result.summary["submitted_count"] == 1

