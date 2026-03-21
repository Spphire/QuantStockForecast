from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from stockmachine.apps import paper_daily


@dataclass(slots=True)
class FakeHealthcheck:
    healthy: bool
    reasons: tuple[str, ...]
    state_readable: bool = False
    state_path: str = ""
    latest_state: dict[str, object] | None = None
    latest_runtime_dir: str | None = None
    open_orders_total: int = 0
    open_orders_for_latest_run: int = 0
    order_journal_rows: int = 0
    data_freshness_meta: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "healthy": self.healthy,
            "reasons": list(self.reasons),
            "state_readable": self.state_readable,
            "state_path": self.state_path,
            "latest_state": self.latest_state,
            "latest_runtime_dir": self.latest_runtime_dir,
            "open_orders_total": self.open_orders_total,
            "open_orders_for_latest_run": self.open_orders_for_latest_run,
            "order_journal_rows": self.order_journal_rows,
            "data_freshness_meta": self.data_freshness_meta or {},
        }


def test_run_command_allows_missing_latest_state(monkeypatch, strategy_bundle_factory, tmp_path: Path) -> None:
    bundle = strategy_bundle_factory(tmp_path)
    captured: dict[str, object] = {}

    monkeypatch.setattr(paper_daily, "read_kill_switch", lambda strategy_id, override="": paper_daily.KillSwitchStatus(
        path=str(tmp_path / "kill"),
        active=False,
        reason="absent",
        payload=None,
    ))
    monkeypatch.setattr(
        paper_daily,
        "build_paper_daily_healthcheck",
        lambda strategy_id: FakeHealthcheck(healthy=False, reasons=("missing_latest_state",)),
    )
    monkeypatch.setattr(
        paper_daily,
        "run_strategy",
        lambda *args, **kwargs: captured.setdefault(
            "result",
            SimpleNamespace(
                summary={"strategy_id": str(bundle["strategy_id"]), "run_id": "run-1"},
                report={"status": "success"},
            ),
        ),
    )

    payload = paper_daily.run_command(
        argparse.Namespace(
            strategy_config=str(bundle["strategy_config"]),
            command="run",
            session_date="2026-03-21",
            submit=False,
            account_equity=100000.0,
            current_positions_csv=str(bundle["current_positions_csv"]),
            output_dir=str(tmp_path / "runtime"),
            ledger_path=str(tmp_path / "paper_ledger.sqlite3"),
            allow_unhealthy=False,
            skip_session_guard=True,
            require_paper=False,
            kill_switch_path="",
            output_format="json",
        )
    )

    assert payload["ok"] is True
    assert payload["preflight"]["policy_allowed"] is True
    assert payload["summary"]["strategy_id"] == str(bundle["strategy_id"])
    assert captured["result"].summary["strategy_id"] == str(bundle["strategy_id"])


def test_run_command_blocks_on_active_kill_switch(monkeypatch, strategy_bundle_factory, tmp_path: Path) -> None:
    bundle = strategy_bundle_factory(tmp_path)

    monkeypatch.setattr(paper_daily, "read_kill_switch", lambda strategy_id, override="": paper_daily.KillSwitchStatus(
        path=str(tmp_path / "kill"),
        active=True,
        reason="manual_stop",
        payload={"active": True},
    ))
    monkeypatch.setattr(
        paper_daily,
        "build_paper_daily_healthcheck",
        lambda strategy_id: FakeHealthcheck(healthy=True, reasons=()),
    )
    monkeypatch.setattr(paper_daily, "run_strategy", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")))

    payload = paper_daily.run_command(
        argparse.Namespace(
            strategy_config=str(bundle["strategy_config"]),
            command="run",
            session_date="2026-03-21",
            submit=False,
            account_equity=100000.0,
            current_positions_csv=str(bundle["current_positions_csv"]),
            output_dir=str(tmp_path / "runtime"),
            ledger_path=str(tmp_path / "paper_ledger.sqlite3"),
            allow_unhealthy=False,
            skip_session_guard=True,
            require_paper=False,
            kill_switch_path="",
            output_format="json",
        )
    )

    assert payload["ok"] is False
    assert payload["summary"]["decision"] == "blocked_preflight"
    assert payload["preflight"]["kill_switch"]["active"] is True


def test_healthcheck_command_uses_strategy_id(monkeypatch, strategy_bundle_factory, tmp_path: Path) -> None:
    bundle = strategy_bundle_factory(tmp_path)
    captured: dict[str, object] = {}

    def fake_healthcheck(strategy_id: str) -> FakeHealthcheck:
        captured["strategy_id"] = strategy_id
        return FakeHealthcheck(healthy=True, reasons=(), state_readable=True, latest_state={"ok": True})

    monkeypatch.setattr(
        paper_daily,
        "build_paper_daily_healthcheck",
        fake_healthcheck,
    )

    payload = paper_daily.healthcheck_command(
        argparse.Namespace(
            strategy_config=str(bundle["strategy_config"]),
            ledger_path="",
            output_format="json",
        )
    )

    assert captured["strategy_id"] == str(bundle["strategy_id"])
    assert payload["ok"] is True
    assert payload["healthcheck"]["latest_state"] == {"ok": True}


def test_read_kill_switch_parses_booleanish_payload(tmp_path: Path) -> None:
    kill_path = tmp_path / "paper_daily.kill"
    kill_path.write_text(json.dumps({"active": False, "reason": "cleared"}), encoding="utf-8")
    inactive = paper_daily.read_kill_switch("demo", override=str(kill_path))
    assert inactive.active is False
    assert inactive.reason == "cleared"

    kill_path.write_text("ON", encoding="utf-8")
    active = paper_daily.read_kill_switch("demo", override=str(kill_path))
    assert active.active is True
