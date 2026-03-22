from __future__ import annotations

import argparse
import json
from pathlib import Path

from execution.managed.apps import paper_brief
from execution.managed.monitoring.briefing import build_feishu_post_payload


def test_research_brief_generates_visual_artifacts(
    isolated_project_root,
    strategy_bundle_factory,
    tmp_path: Path,
) -> None:
    bundle = strategy_bundle_factory(tmp_path, strategy_id="research_demo")
    config_path = Path(bundle["strategy_config"])
    config = json.loads(config_path.read_text(encoding="utf-8"))

    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "model_name": "demo_research",
                "annualized_return": 0.21,
                "excess_total_return": 0.12,
                "win_rate": 0.57,
                "max_drawdown": -0.18,
                "periods": 42,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    config["source"]["summary_path"] = str(summary_path)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = paper_brief.dispatch_command(
        argparse.Namespace(
            strategy_configs=[str(config_path)],
            phase="research",
            title="Research Test Brief",
            output_root=str(tmp_path / "briefs"),
            output_format="json",
        )
    )

    assert payload["ok"] is True
    assert Path(payload["dashboard_png"]).exists()
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["html_path"]).exists()
    assert payload["summary"]["positive_target_count"] == 2
    assert payload["summary"]["exit_count"] == 1
    assert payload["strategies"][0]["source_summary"]["model_name"] == "demo_research"
    markdown_text = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "调仓日期" in markdown_text
    assert "下一步建议" in markdown_text
    brief_json = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    post_payload = build_feishu_post_payload(
        brief=brief_json,
        run_dir=Path(payload["run_dir"]),
        html_path=Path(payload["html_path"]),
    )
    assert post_payload["msg_type"] == "post"
    research_text = "\n".join(
        block["text"]
        for row in post_payload["content"]["post"]["zh_cn"]["content"]
        for block in row
        if block.get("tag") == "text"
    )
    assert "总览：" in research_text
    assert "重点仓位：" in research_text


def test_submit_brief_reads_latest_state_and_order_statuses(
    isolated_project_root,
    strategy_bundle_factory,
    tmp_path: Path,
) -> None:
    bundle = strategy_bundle_factory(tmp_path, strategy_id="submit_demo")
    strategy_id = str(bundle["strategy_id"])
    config_path = Path(bundle["strategy_config"])

    runtime_dir = tmp_path / "execution" / "runtime" / strategy_id / "20260322T010203Z"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    target_positions_path = runtime_dir / "target_positions.csv"
    target_positions_path.write_bytes(Path(bundle["source_csv"]).read_bytes())

    summary_path = tmp_path / "summary_submit.json"
    summary_path.write_text(
        json.dumps(
            {
                "model_name": "demo_submit",
                "annualized_return": 0.11,
                "excess_total_return": 0.03,
                "win_rate": 0.52,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    account_path = runtime_dir / "post_account_snapshot.json"
    account_path.write_text(
        json.dumps(
            {
                "broker": "alpaca",
                "equity": 100000.0,
                "cash": 100000.0,
                "buying_power": 103000.0,
                "currency": "USD",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    statuses_path = runtime_dir / "submitted_order_statuses.json"
    statuses_path.write_text(
        json.dumps(
            [
                {"symbol": "AAA", "status": "accepted"},
                {"symbol": "BBB", "status": "filled"},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state_dir = tmp_path / "execution" / "state" / strategy_id
    state_dir.mkdir(parents=True, exist_ok=True)
    latest_state_path = state_dir / "latest_state.json"
    latest_state_path.write_text(
        json.dumps(
            {
                "strategy_id": strategy_id,
                "rebalance_date": "2026-03-21",
                "targets_csv_path": str(target_positions_path),
                "source_summary_path": str(summary_path),
                "account_path": str(account_path),
                "submitted_order_statuses_path": str(statuses_path),
                "account_equity": 100000.0,
                "planning_equity": 97000.0,
                "account_buying_power": 103000.0,
                "submitted_count": 2,
                "run_dir": str(runtime_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = paper_brief.dispatch_command(
        argparse.Namespace(
            strategy_configs=[str(config_path)],
            phase="submit",
            title="Submit Test Brief",
            output_root=str(tmp_path / "briefs"),
            output_format="json",
        )
    )

    strategy_payload = payload["strategies"][0]
    assert payload["ok"] is True
    assert Path(payload["json_path"]).exists()
    assert strategy_payload["submitted_count"] == 2
    assert strategy_payload["open_order_count"] == 1
    assert strategy_payload["account"]["buying_power"] == 103000.0
    assert strategy_payload["alerts"][0]["code"] == "open_orders_lingering"

    brief_json = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    post_payload = build_feishu_post_payload(
        brief=brief_json,
        run_dir=Path(payload["run_dir"]),
        html_path=Path(payload["html_path"]),
    )
    assert post_payload["msg_type"] == "post"
    assert post_payload["content"]["post"]["zh_cn"]["title"] == "Submit Test Brief"
