from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from PIL import Image

from execution.managed.briefing.chart_assets import generate_brief_chart_assets
from execution.managed.briefing.html_templates import render_submit_html
from execution.managed.briefing.presenter import format_generated_time_cn, strategy_cn_name
from execution.managed.apps import paper_brief
from execution.managed.monitoring import briefing as monitoring_briefing
from execution.managed.monitoring.briefing import build_feishu_post_payload


def _write_submit_state(
    *,
    tmp_path: Path,
    strategy_bundle_factory,
    strategy_id: str,
    statuses: list[dict[str, str]],
    submitted_count: int = 2,
) -> tuple[dict[str, object], Path, Path, Path]:
    bundle = strategy_bundle_factory(tmp_path, strategy_id=strategy_id)
    config_path = Path(bundle["strategy_config"])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["broker"] = "alpaca"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    runtime_dir = tmp_path / "execution" / "runtime" / strategy_id / "20260322T010203Z"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    target_positions_path = runtime_dir / "target_positions.csv"
    target_positions_path.write_bytes(Path(bundle["source_csv"]).read_bytes())

    summary_path = tmp_path / f"summary_{strategy_id}.json"
    summary_path.write_text(
        json.dumps(
            {
                "model_name": f"demo_{strategy_id}",
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
    statuses_path.write_text(json.dumps(statuses, ensure_ascii=False, indent=2), encoding="utf-8")

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
                "submitted_count": submitted_count,
                "run_dir": str(runtime_dir),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return bundle, config_path, runtime_dir, latest_state_path


def _patch_live_refresh(
    monkeypatch,
    *,
    refresh_payload: dict[str, object] | None = None,
) -> None:
    if refresh_payload is None:

        def _unexpected_refresh(**kwargs):
            raise AssertionError("live Alpaca refresh should not run for non-final submit states")

        monkeypatch.setattr(monitoring_briefing, "_try_refresh_live_alpaca_snapshot", _unexpected_refresh, raising=False)
    else:
        monkeypatch.setattr(
            monitoring_briefing,
            "_try_refresh_live_alpaca_snapshot",
            lambda **kwargs: dict(refresh_payload),
            raising=False,
        )


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
            title="研究简报测试",
            output_root=str(tmp_path / "briefs"),
            output_format="json",
        )
    )

    assert payload["ok"] is True
    dashboard_path = Path(payload["dashboard_png"])
    assert dashboard_path.exists()
    image = Image.open(dashboard_path)
    aspect_ratio = image.height / image.width
    assert 1.30 < aspect_ratio < 1.50
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
        image_key="img_v3_demo_key",
    )
    assert post_payload["msg_type"] == "post"
    research_rows = post_payload["content"]["post"]["zh_cn"]["content"]
    assert research_rows[0][0]["tag"] == "img"
    assert research_rows[0][0]["image_key"] == "img_v3_demo_key"
    research_text = "\n".join(
        block["text"]
        for row in research_rows
        for block in row
        if block.get("tag") == "text"
    )
    assert "总览：" in research_text
    assert "重点仓位：" in research_text
    assert "专家一致性：" in research_text
    assert "结论：" in research_text
    assert "北京时间：" in research_text


@pytest.mark.parametrize(
    "statuses, expected_execution_state, expected_status, expected_alert_code, refresh_payload",
    [
        (
            [
                {"symbol": "AAA", "status": "filled"},
                {"symbol": "BBB", "status": "filled"},
            ],
            "final",
            "success",
            None,
            {
                "attempted": True,
                "ok": True,
                "reason": "live_alpaca",
                "account_snapshot": {
                    "broker": "alpaca",
                    "equity": 105000.0,
                    "cash": 25000.0,
                    "buying_power": 107000.0,
                    "currency": "USD",
                },
                "positions_snapshot": [
                    {"symbol": "AAA", "market_value": 44000.0},
                    {"symbol": "BBB", "market_value": 36000.0},
                ],
            },
        ),
        (
            [
                {"symbol": "AAA", "status": "accepted"},
                {"symbol": "BBB", "status": "filled"},
            ],
            "provisional",
            "partial",
            "open_orders_lingering",
            None,
        ),
        (
            [
                {"symbol": "AAA", "status": "rejected"},
                {"symbol": "BBB", "status": "rejected"},
            ],
            "final",
            "failed",
            None,
            {
                "attempted": True,
                "ok": True,
                "reason": "live_alpaca",
                "account_snapshot": {
                    "broker": "alpaca",
                    "equity": 105000.0,
                    "cash": 25000.0,
                    "buying_power": 107000.0,
                    "currency": "USD",
                },
                "positions_snapshot": [
                    {"symbol": "AAA", "market_value": 44000.0},
                    {"symbol": "BBB", "market_value": 36000.0},
                ],
            },
        ),
    ],
)
def test_submit_brief_maps_execution_state_and_status(
    isolated_project_root,
    strategy_bundle_factory,
    tmp_path: Path,
    monkeypatch,
    statuses,
    expected_execution_state,
    expected_status,
    expected_alert_code,
    refresh_payload,
) -> None:
    _, config_path, _, _ = _write_submit_state(
        tmp_path=tmp_path,
        strategy_bundle_factory=strategy_bundle_factory,
        strategy_id="submit_demo",
        statuses=statuses,
    )
    _patch_live_refresh(monkeypatch, refresh_payload=refresh_payload)

    payload = paper_brief.dispatch_command(
        argparse.Namespace(
            strategy_configs=[str(config_path)],
            phase="submit",
            title="提交简报测试",
            output_root=str(tmp_path / "briefs"),
            output_format="json",
        )
    )

    strategy_payload = payload["strategies"][0]
    assert payload["ok"] is True
    assert payload["status"] == expected_status
    assert payload["status_display"] == {"success": "运行正常", "partial": "需要关注", "failed": "运行失败"}[expected_status]
    assert payload["rendering"]["renderer"] == "html_playwright"
    dashboard_path = Path(payload["dashboard_png"])
    assert dashboard_path.exists()
    image = Image.open(dashboard_path)
    aspect_ratio = image.height / image.width
    assert 1.30 < aspect_ratio < 1.50
    assert Path(payload["json_path"]).exists()
    assert payload["execution_state"] == expected_execution_state
    assert strategy_payload["execution_state"] == expected_execution_state
    assert strategy_payload["submitted_count"] == 2
    if refresh_payload is not None:
        assert strategy_payload["distribution_source"] == "live_alpaca"
        assert strategy_payload["distribution_refresh"]["ok"] is True
        assert strategy_payload["distribution_refresh"]["reason"] == "live_alpaca"
        assert strategy_payload["account"]["cash"] == 25000.0
        assert strategy_payload["account"]["buying_power"] == 103000.0
        assert strategy_payload["current_distribution"] and {item["label"] for item in strategy_payload["current_distribution"]} == {"AAA", "BBB", "现金"}
    else:
        assert strategy_payload["distribution_source"] == "state_snapshot"
        assert strategy_payload["distribution_refresh"]["attempted"] is False
        if expected_status == "partial":
            assert strategy_payload["distribution_refresh"]["reason"] == "orders_not_final"
            assert strategy_payload["open_order_count"] == 1
    if expected_status == "failed":
        assert strategy_payload["has_rejected_orders"] is True
    if expected_alert_code is None:
        assert not strategy_payload["alerts"]
    else:
        assert any(alert["code"] == expected_alert_code for alert in strategy_payload["alerts"])

    brief_json = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    post_payload = build_feishu_post_payload(
        brief=brief_json,
        run_dir=Path(payload["run_dir"]),
        html_path=Path(payload["html_path"]),
        image_key="img_v3_submit_demo",
    )
    assert post_payload["msg_type"] == "post"
    submit_rows = post_payload["content"]["post"]["zh_cn"]["content"]
    assert submit_rows[0][0]["tag"] == "img"
    assert submit_rows[0][0]["image_key"] == "img_v3_submit_demo"
    submit_text = "\n".join(
        block["text"]
        for row in submit_rows
        for block in row
        if block.get("tag") == "text"
    )
    assert f"状态：{payload['status_display']}" in submit_text
    assert "调仓：" in submit_text
    assert "重点仓位：" in submit_text
    assert "提示：" in submit_text
    assert "预计5日收益" not in submit_text
    assert "下单后预计趋势" not in submit_text

    html_text = Path(payload["html_path"]).read_text(encoding="utf-8")
    assert "下单后预计趋势" not in html_text
    assert "预计5日收益" not in html_text
    assert html_text.count('class="chart-card"') == 3


def test_submit_notification_policy_blocks_provisional(monkeypatch, tmp_path: Path) -> None:
    config_payload = {
        "feishu": {
            "enabled": True,
            "webhook_url": "https://example.invalid/hook",
            "upload_dashboard_image": False,
            "submit_brief_policy": "final_only",
        }
    }
    monkeypatch.setattr(monitoring_briefing, "_load_json_mapping", lambda *_args, **_kwargs: config_payload, raising=False)

    def _unexpected_post(*args, **kwargs):
        raise AssertionError("webhook should not be called for provisional submit under final_only policy")

    monkeypatch.setattr(monitoring_briefing.requests, "post", _unexpected_post, raising=False)

    brief = {
        "phase": "submit",
        "execution_state": "provisional",
        "status_display": "需要关注",
        "generated_at_utc": "2026-03-22T00:00:00+00:00",
        "summary": {},
        "strategies": [],
    }
    result = monitoring_briefing._maybe_send_notifications(
        brief=brief,
        run_dir=tmp_path,
        html_path=tmp_path / "brief.html",
        dashboard_path=tmp_path / "dashboard.png",
    )
    assert result["sent"] is False
    assert result["reason"] == "submit_policy_blocked:final_only:provisional"


def test_feishu_payload_can_embed_uploaded_image() -> None:
    payload = build_feishu_post_payload(
        brief={
            "title": "图文简报",
            "status_display": "运行正常",
            "generated_at_utc": "2026-03-22T00:00:00+00:00",
            "summary": {
                "strategy_count": 2,
                "positive_target_count": 8,
                "submitted_count": 6,
                "open_order_count": 1,
            },
            "strategies": [],
        },
        run_dir=Path("C:/tmp/run"),
        html_path=Path("C:/tmp/run/brief.html"),
        image_key="img_v3_demo_key",
    )

    content_rows = payload["content"]["post"]["zh_cn"]["content"]
    assert content_rows[0][0]["tag"] == "img"
    assert content_rows[0][0]["image_key"] == "img_v3_demo_key"


def test_submit_chart_assets_expose_only_three_charts(tmp_path: Path) -> None:
    brief = {
        "phase": "submit",
        "strategies": [
            {
                "strategy_id": "submit_demo",
                "strategy_name": "submit_demo",
                "strategy_alias": "submit_demo",
                "rebalance_date": "2026-03-21",
                "explain_like_human": "提交简报占位",
                "top_positions_text": "AAA 40%, BBB 30%",
                "submitted_count": 2,
                "open_order_count": 1,
                "agreement_ratio": 0.0,
                "expected_portfolio_return": 0.0,
                "research_conclusion": "",
                "alerts": [],
                "current_distribution": [
                    {"label": "AAA", "value": 44000.0},
                    {"label": "BBB", "value": 36000.0},
                    {"label": "现金", "value": 25000.0},
                ],
                "equity_curve": [
                    {"date": "2026-03-20", "equity": 100000.0},
                    {"date": "2026-03-21", "equity": 105000.0},
                ],
                "top_positions": [
                    {"symbol": "AAA", "target_weight": 0.4, "score": 0.9},
                    {"symbol": "BBB", "target_weight": 0.3, "score": 0.7},
                ],
            }
        ],
    }

    chart_payload = generate_brief_chart_assets(brief=brief, output_dir=tmp_path / "charts")
    strategy_charts = chart_payload["strategies"][0]["charts"]
    assert "current_distribution_pie" in strategy_charts
    assert "total_pnl_curve" in strategy_charts
    assert "signal_strength" in strategy_charts
    assert "projection" not in strategy_charts
    assert strategy_charts.get("symbol_curve") == strategy_charts["signal_strength"]


def test_submit_html_template_uses_three_cards_and_omits_projection() -> None:
    brief = {
        "phase": "submit",
        "title": "开盘执行简报",
        "status": "partial",
        "status_display": "需要关注",
        "generated_at_utc": "2026-03-22T00:00:00+00:00",
        "summary": {
            "strategy_count": 1,
            "positive_target_count": 2,
            "submitted_count": 2,
            "open_order_count": 1,
        },
        "strategies": [],
    }
    chart_payload = {
        "phase": "submit",
        "strategies": [
            {
                "strategy_id": "submit_demo",
                "strategy_name": "submit_demo",
                "strategy_alias": "submit_demo",
                "rebalance_date": "2026-03-21",
                "explain_like_human": "AAA 已提交，BBB 仍在等待成交。",
                "top_positions_text": "AAA 40%, BBB 30%",
                "submitted_count": 2,
                "open_order_count": 1,
                "agreement_ratio": 0.0,
                "expected_portfolio_return": 0.0,
                "research_conclusion": "",
                "alerts": [{"code": "open_orders_lingering", "title": "仍有未完成订单"}],
                "chart_explanations": {
                    "current_distribution_pie": "当前仓位分布",
                    "total_pnl_curve": "账户权益曲线",
                    "signal_strength": "单股信号强弱",
                },
                "charts": {
                    "current_distribution_pie": "dist.png",
                    "total_pnl_curve": "curve.png",
                    "signal_strength": "signal.png",
                    "symbol_curve": "signal.png",
                },
            }
        ],
    }

    html = render_submit_html(brief=brief, chart_payload=chart_payload)
    assert "下单后预计趋势" not in html
    assert "预计5日收益" not in html
    assert "projection" not in html
    assert html.count('class="chart-card"') == 3
    assert "当前账户持仓分布（含现金）" in html
    assert "账户权益曲线（现金+持仓）" in html
    assert "单股信号强度（归一分位）" in html


def test_presenter_cn_helpers() -> None:
    assert strategy_cn_name("us_zeroshot_a_share_multi_expert_daily").startswith("A股训练零样本")
    assert strategy_cn_name("us_full_multi_expert_daily").startswith("美股全量训练")
    assert format_generated_time_cn("2026-03-22T07:30:00+00:00") == "2026-03-22 15:30:00"
