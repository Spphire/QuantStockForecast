from __future__ import annotations

import argparse

from stockmachine.apps import paper_smoke


def test_build_smoke_payload_includes_recommended_commands(monkeypatch, strategy_bundle_factory, tmp_path) -> None:
    bundle = strategy_bundle_factory(tmp_path)

    monkeypatch.setattr(
        paper_smoke.paper_daily,
        "run_command",
        lambda args: {
            "ok": True,
            "summary": {"strategy_id": "demo", "run_id": "run-1"},
            "report": {"status": "success"},
        },
    )

    payload = paper_smoke.build_smoke_payload(
        argparse.Namespace(
            strategy_config=str(bundle["strategy_config"]),
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
        )
    )

    assert payload["command"] == "smoke"
    assert payload["ok"] is True
    assert payload["run"]["summary"]["strategy_id"] == "demo"
    assert payload["recommended_commands"]["healthcheck"][:3] == ["python", "-m", "stockmachine.apps.paper_daily"]
    assert payload["recommended_commands"]["healthcheck"][4] == "healthcheck"
