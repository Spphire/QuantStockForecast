from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


def _install_live_stubs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    live_dir = repo_root / "src" / "stockmachine" / "live"

    live_pkg = sys.modules.get("stockmachine.live")
    if live_pkg is None:
        live_pkg = types.ModuleType("stockmachine.live")
        live_pkg.__path__ = [str(live_dir)]
        sys.modules["stockmachine.live"] = live_pkg

    if "stockmachine.live.reconciler" not in sys.modules:
        reconciler = types.ModuleType("stockmachine.live.reconciler")

        class PollingOrderReconciler:
            def __init__(self, ledger: Any) -> None:
                self.ledger = ledger
                self.last_order_statuses: tuple[dict[str, Any], ...] = ()

            def reconcile_orders(self, order_statuses: list[dict[str, Any]]) -> dict[str, int]:
                self.last_order_statuses = tuple(dict(item) for item in order_statuses)
                return {"reconciled": len(order_statuses)}

        reconciler.PollingOrderReconciler = PollingOrderReconciler
        sys.modules["stockmachine.live.reconciler"] = reconciler

    if "stockmachine.live.recovery" not in sys.modules:
        recovery = types.ModuleType("stockmachine.live.recovery")

        @dataclass(slots=True)
        class _Plan:
            aligned_count: int
            orphan_count: int
            stale_count: int

        @dataclass(slots=True)
        class _Reconciliation:
            created_orders: int
            updated_orders: int
            fill_events_created: int

        @dataclass(slots=True)
        class _RecoveryResult:
            plan: _Plan
            reconciliation: _Reconciliation

        def recover_open_orders(ledger: Any, open_orders: tuple[dict[str, Any], ...], reconciler: Any) -> _RecoveryResult:
            del ledger, reconciler
            count = len(open_orders)
            return _RecoveryResult(
                plan=_Plan(aligned_count=count, orphan_count=0, stale_count=0),
                reconciliation=_Reconciliation(created_orders=0, updated_orders=0, fill_events_created=0),
            )

        recovery.recover_open_orders = recover_open_orders
        sys.modules["stockmachine.live.recovery"] = recovery

    if "stockmachine.live.session_guard" not in sys.modules:
        session_guard = types.ModuleType("stockmachine.live.session_guard")

        @dataclass(slots=True)
        class SessionGuardRequest:
            ledger: Any
            strategy_name: str
            session_date: Any
            dry_run: bool
            silver_session_dates: tuple[Any, ...]
            allow_previous_available_session: bool

        @dataclass(slots=True)
        class SessionGuardResult:
            allowed: bool
            effective_session_date: Any
            reasons: tuple[str, ...] = ()
            details: dict[str, Any] | None = None

            def to_dict(self) -> dict[str, Any]:
                return {
                    "allowed": self.allowed,
                    "effective_session_date": self.effective_session_date.isoformat()
                    if hasattr(self.effective_session_date, "isoformat")
                    else self.effective_session_date,
                    "reasons": list(self.reasons),
                    "details": dict(self.details or {}),
                }

        class SessionGuard:
            def __init__(self, ledger: Any) -> None:
                self.ledger = ledger

            def evaluate(self, request: SessionGuardRequest) -> SessionGuardResult:
                return SessionGuardResult(
                    allowed=True,
                    effective_session_date=request.session_date,
                    reasons=(),
                    details={"dry_run": request.dry_run},
                )

        session_guard.SessionGuard = SessionGuard
        session_guard.SessionGuardRequest = SessionGuardRequest
        sys.modules["stockmachine.live.session_guard"] = session_guard


_install_live_stubs()


@pytest.fixture
def isolated_project_root(tmp_path, monkeypatch):
    import execution.common.state_store as state_store
    import execution.common.strategy_runtime as strategy_runtime
    import stockmachine.monitoring.healthcheck as healthcheck

    monkeypatch.setattr(state_store, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(strategy_runtime, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(healthcheck, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(healthcheck, "DEFAULT_STATE_ROOT", tmp_path / "execution" / "state")
    return tmp_path


@pytest.fixture
def strategy_bundle_factory():
    def _factory(
        tmp_path: Path,
        *,
        strategy_id: str = "demo_strategy",
        rebalance_dates: tuple[str, ...] = ("2026-03-21",),
    ) -> dict[str, Path | str]:
        source_csv = tmp_path / "risk_positions.csv"
        actions_csv = tmp_path / "risk_actions.csv"
        positions_csv = tmp_path / "current_positions.csv"
        config_json = tmp_path / "strategy.json"

        pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "target_weight": 0.50,
                    "previous_weight": 0.10,
                    "action": "hold",
                    "reference_price": 100.0,
                    "score": 0.90,
                    "confidence": 0.80,
                    "rebalance_date": rebalance_dates[0],
                    "model_mode": "multi_expert",
                    "industry_group": "tech",
                    "name": "Alpha",
                },
                {
                    "symbol": "BBB",
                    "target_weight": 0.40,
                    "previous_weight": 0.20,
                    "action": "hold",
                    "reference_price": 100.0,
                    "score": 0.85,
                    "confidence": 0.75,
                    "rebalance_date": rebalance_dates[0],
                    "model_mode": "multi_expert",
                    "industry_group": "health",
                    "name": "Beta",
                },
            ]
        ).to_csv(source_csv, index=False, encoding="utf-8")

        pd.DataFrame(
            [
                {
                    "symbol": "CCC",
                    "target_weight": 0.0,
                    "previous_weight": 0.2,
                    "action": "exit",
                    "reference_price": 100.0,
                    "score": 0.10,
                    "confidence": 0.20,
                    "rebalance_date": rebalance_dates[0],
                    "model_mode": "multi_expert",
                    "industry_group": "energy",
                    "name": "Gamma",
                },
                {
                    "symbol": "DDD",
                    "target_weight": 0.15,
                    "previous_weight": 0.0,
                    "action": "hold",
                    "reference_price": 100.0,
                    "score": 0.50,
                    "confidence": 0.50,
                    "rebalance_date": rebalance_dates[-1] if len(rebalance_dates) > 1 else rebalance_dates[0],
                    "model_mode": "multi_expert",
                    "industry_group": "industrial",
                    "name": "Delta",
                },
            ]
        ).to_csv(actions_csv, index=False, encoding="utf-8")

        pd.DataFrame(
            [
                {"symbol": "AAA", "qty": 0, "market_value": 0, "current_price": 100},
                {"symbol": "BBB", "qty": 100, "market_value": 10000, "current_price": 100},
                {"symbol": "CCC", "qty": 200, "market_value": 20000, "current_price": 100},
            ]
        ).to_csv(positions_csv, index=False, encoding="utf-8")

        config_json.write_text(
            json.dumps(
                {
                    "strategy_id": strategy_id,
                    "broker": "alpaca",
                    "market": "US",
                    "paper_env_prefix": "ALPACA_PAPER",
                    "source": {
                        "type": "risk_positions_csv",
                        "path": str(source_csv),
                        "actions_path": str(actions_csv),
                        "summary_path": str(tmp_path / "summary.csv"),
                    },
                    "execution": {
                        "rebalance_selection": "latest",
                        "default_account_equity": 100000.0,
                        "buying_power_buffer": 1.0,
                        "allow_fractional": True,
                        "order_sizing_mode": "notional",
                        "order_type": "market",
                        "time_in_force": "day",
                        "cancel_open_orders_first": True,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "strategy_config": config_json,
            "source_csv": source_csv,
            "actions_csv": actions_csv,
            "current_positions_csv": positions_csv,
            "strategy_id": strategy_id,
        }

    return _factory
