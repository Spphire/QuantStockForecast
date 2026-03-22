from __future__ import annotations

import ast
import base64
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import shutil
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

import matplotlib.pyplot as plt
import pandas as pd
import requests

from execution.alpaca.client import AlpacaBroker, load_alpaca_credentials
from execution.common.strategy_runtime import load_strategy_config, load_target_positions
from execution.managed.briefing.sections import (
    build_current_distribution as _build_current_distribution,
    build_expected_projection as _build_expected_projection,
    build_expert_snapshot as _build_expert_snapshot,
    build_research_conclusion as _build_research_conclusion,
    build_symbol_price_curves as _build_symbol_price_curves,
    infer_model_name_hint as _infer_model_name_hint,
    load_equity_curve as _load_equity_curve,
    load_source_frame as _load_source_frame,
    select_submit_curve_symbols as _select_submit_curve_symbols,
)
from execution.managed.briefing.presenter import (
    compact_action_text as _compact_action_text,
    format_generated_time_cn as _format_generated_time_cn,
    strategy_cn_name as _strategy_cn_name,
    top_positions_text as _top_positions_text,
)
from execution.managed.briefing.html_renderer import render_operation_brief_html_page as _render_operation_brief_html_page
from execution.managed.briefing.poster import render_operation_brief_poster as _render_operation_brief_poster
from execution.managed.monitoring.alerts import TERMINAL_ORDER_STATUSES, build_operator_alerts
from execution.managed.monitoring.healthcheck import build_paper_daily_healthcheck


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BRIEF_ROOT = PROJECT_ROOT / "artifacts" / "ops_briefs"
DEFAULT_NOTIFICATION_CONFIG = PROJECT_ROOT / "configs" / "ops_notifications.local.json"

PHASE_TITLES = {"research": "夜间研究简报", "submit": "开盘执行简报"}
PHASE_LABELS = {"research": "夜间研究", "submit": "开盘执行"}
STATUS_STYLES = {
    "success": {"label": "运行正常", "color": "#0b6e4f", "background": "#dff3ea"},
    "partial": {"label": "需要关注", "color": "#9c6500", "background": "#fff2d8"},
    "failed": {"label": "运行失败", "color": "#9b1c1c", "background": "#fde4e1"},
}
PIE_COLORS = ["#0b6e4f", "#1b998b", "#ffb703", "#e76f51", "#8ecae6", "#adb5bd"]
BAR_COLORS = ["#1d3557", "#457b9d", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"]
A4_LANDSCAPE = (11.69, 8.27)
ACTION_LABELS = {"open": "开仓", "add": "加仓", "reduce": "减仓", "hold": "持有", "exit": "退出", "accepted": "已受理", "filled": "已成交", "rejected": "被拒绝", "canceled": "已撤单", "cancelled": "已撤单", "expired": "已过期"}
ALERT_SEVERITY_LABELS = {"info": "提示", "warning": "提醒", "critical": "严重"}
ALERT_COPY = {
    "data_stale": {
        "title": "行情数据已过期",
        "message": "最近一次运行引用的数据 session 已超出新鲜度窗口，建议先更新研究产物再执行。",
    },
    "duplicate_run_blocked": {
        "title": "重复运行已被拦截",
        "message": "系统检测到重复 paper run，并已由保护机制阻止重复执行。",
    },
    "broker_rejection": {
        "title": "券商拒绝了订单",
        "message": "有一笔或多笔订单被券商拒绝，需要检查下单参数或账户状态。",
    },
    "open_orders_lingering": {
        "title": "仍有未完成订单",
        "message": "最近一次运行后，券商侧仍存在未进入终态的订单。",
    },
}
DEFAULT_EXPERT_INPUT_WINDOWS = {
    "lightgbm": 60,
    "xgboost": 60,
    "catboost": 60,
    "lstm": 20,
    "transformer": 20,
}


def generate_operation_brief(
    *,
    strategy_configs: Sequence[str | Path],
    phase: str,
    output_root: str | Path | None = None,
    title: str = "",
    status: str = "success",
    notes: Sequence[str] | None = None,
    reference_date: date | None = None,
    notify: bool = False,
) -> dict[str, Any]:
    if phase not in PHASE_TITLES:
        raise ValueError(f"Unsupported phase: {phase}")
    if status not in STATUS_STYLES:
        raise ValueError(f"Unsupported brief status: {status}")

    strategies = [
        build_strategy_brief(strategy_config=Path(path), phase=phase, reference_date=reference_date)
        for path in strategy_configs
    ]
    effective_status = _derive_submit_brief_status(strategies=strategies, requested_status=status) if phase == "submit" else status
    execution_state = _derive_submit_execution_state(strategies=strategies) if phase == "submit" else "research"

    brief = {
        "phase": phase,
        "title": title or PHASE_TITLES[phase],
        "status": effective_status,
        "status_display": STATUS_STYLES[effective_status]["label"],
        "execution_state": execution_state,
        "notes": [str(note).strip() for note in (notes or ()) if str(note).strip()],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference_date": (reference_date or date.today()).isoformat(),
        "strategies": strategies,
    }
    brief["strategy_count"] = len(brief["strategies"])
    brief["summary"] = _build_summary(brief["strategies"], phase=phase, status=effective_status)

    root = Path(output_root) if output_root else DEFAULT_BRIEF_ROOT / phase
    run_dir = root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = run_dir / "dashboard.png"
    markdown_path = run_dir / "brief.md"
    html_path = run_dir / "brief.html"
    json_path = run_dir / "brief.json"

    rendering = _render_visual_artifacts(
        brief=brief,
        run_dir=run_dir,
        dashboard_path=dashboard_path,
        html_path=html_path,
    )
    markdown_path.write_text(_build_markdown(brief, dashboard_path.name), encoding="utf-8")
    if not html_path.exists():
        html_path.write_text(_build_html(brief, dashboard_path.name), encoding="utf-8")
    json_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_dir = root / "latest"
    _sync_latest(run_dir, latest_dir)
    notification = (
        _maybe_send_notifications(
            brief=brief,
            run_dir=run_dir,
            html_path=html_path,
            dashboard_path=dashboard_path,
        )
        if notify
        else {"enabled": False, "reason": "notify_disabled"}
    )

    return {
        "ok": True,
        "phase": phase,
        "title": brief["title"],
        "status": brief["status"],
        "status_display": brief["status_display"],
        "execution_state": brief["execution_state"],
        "notes": brief["notes"],
        "generated_at_utc": brief["generated_at_utc"],
        "run_dir": str(run_dir),
        "latest_dir": str(latest_dir),
        "dashboard_png": str(dashboard_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "json_path": str(json_path),
        "rendering": rendering,
        "notification": notification,
        "summary": brief["summary"],
        "strategies": brief["strategies"],
    }


def build_strategy_brief(*, strategy_config: str | Path, phase: str, reference_date: date | None = None) -> dict[str, Any]:
    config_path = Path(strategy_config)
    config = load_strategy_config(config_path)
    strategy_id = str(config["strategy_id"])
    broker_name = _normalize(config.get("broker") or "alpaca")
    paper_env_prefix = str(config.get("paper_env_prefix") or "").strip()
    source = dict(config.get("source") or {})
    execution = dict(config.get("execution") or {})
    healthcheck = build_paper_daily_healthcheck(strategy_id, reference_date=reference_date)
    latest_state = dict(healthcheck.latest_state or {})
    if phase != "submit":
        latest_state = {}
    source_path = latest_state.get("targets_csv_path") if phase == "submit" else source.get("path")
    resolved_source_path = _resolve_path(source_path or source.get("path"))
    actions_path = None if phase == "submit" else source.get("actions_path")
    targets = _load_targets(source_path=source_path or source.get("path"), actions_path=actions_path, rebalance_selection=str(execution.get("rebalance_selection") or "latest"))
    target_rows = [target.to_dict() for target in targets]
    positive_targets = [row for row in target_rows if (_coerce_float(row.get("target_weight")) or 0.0) > 0]
    positive_targets.sort(key=lambda item: _coerce_float(item.get("target_weight")) or 0.0, reverse=True)
    exit_rows = [row for row in target_rows if str(row.get("action", "")).lower() == "exit" or (_coerce_float(row.get("target_weight")) or 0.0) <= 0.0]
    order_statuses = _load_json_list(latest_state.get("submitted_order_statuses_path")) if phase == "submit" else []
    submitted_count = int(latest_state.get("submitted_count") or len(order_statuses))
    settlement = (
        _classify_submit_order_fulfillment(order_statuses=order_statuses, submitted_count=submitted_count)
        if phase == "submit"
        else {
            "submitted_count": submitted_count,
            "status_count": 0,
            "terminal_order_count": 0,
            "open_order_count": 0,
            "rejected_count": 0,
            "has_rejected": False,
            "coverage": "n/a",
            "is_final": True,
            "execution_state": "research",
        }
    )
    execution_state = str(settlement.get("execution_state") or ("research" if phase != "submit" else "provisional"))
    open_order_count = int(settlement.get("open_order_count") or 0)
    alerts = [_localize_alert(alert.to_dict()) for alert in build_operator_alerts(state_payload=latest_state, reference_date=reference_date)] if phase == "submit" else []
    source_summary = _load_json_mapping((latest_state.get("source_summary_path") or source.get("summary_path"))) if (phase == "submit" or source.get("summary_path")) else {}
    account_snapshot = _load_json_mapping(latest_state.get("account_path")) if phase == "submit" else {}
    positions_snapshot = _load_json_list(latest_state.get("positions_path")) if phase == "submit" else []
    distribution_source = "state_snapshot" if phase == "submit" else "snapshot"
    distribution_refresh: dict[str, Any] = {"attempted": False, "ok": False, "reason": ("not_submit_phase" if phase != "submit" else "orders_not_final")}
    if phase == "submit" and execution_state == "final":
        if broker_name != "alpaca":
            distribution_refresh = {"attempted": False, "ok": False, "reason": "broker_not_alpaca"}
        else:
            distribution_refresh = _try_refresh_live_alpaca_snapshot(paper_env_prefix=paper_env_prefix)
            if bool(distribution_refresh.get("ok")):
                account_snapshot = dict(distribution_refresh.get("account_snapshot") or {})
                positions_snapshot = [
                    dict(item)
                    for item in list(distribution_refresh.get("positions_snapshot") or [])
                    if isinstance(item, Mapping)
                ]
                distribution_source = "live_alpaca"
    buffer = _coerce_float(latest_state.get("buying_power_buffer")) or _coerce_float(execution.get("buying_power_buffer")) or 1.0
    account_equity = _coerce_float(latest_state.get("account_equity")) or _coerce_float(account_snapshot.get("equity")) or _coerce_float(execution.get("default_account_equity")) or 0.0
    planning_equity = _coerce_float(latest_state.get("planning_equity")) or (account_equity * buffer)
    top_positions = [_decorate_target(row, planning_equity) for row in positive_targets[:5]]
    rebalance_date = _latest_rebalance_date(target_rows) or latest_state.get("rebalance_date") or ""
    top_symbols = [str(item.get("symbol", "")).upper() for item in top_positions if str(item.get("symbol", "")).strip()]
    source_frame = _load_source_frame(resolved_source_path)
    research_cfg = dict(config.get("research") or {})
    analysis_cfg = dict(config.get("analysis") or {})
    market_curve_frame, market_curve_source = _resolve_research_curve_source_frame(
        config=config,
        config_path=config_path,
        fallback_source_frame=source_frame,
    )
    watchlist_limit = int(
        max(
            3,
            min(
                30,
                (_coerce_float(research_cfg.get("watchlist_limit")) or _coerce_float(analysis_cfg.get("watchlist_limit")) or 10.0),
            ),
        )
    )
    pool_symbols, pool_source = _extract_analysis_pool_symbols(
        config=config,
        config_path=config_path,
        source_frame=market_curve_frame,
        rebalance_date=rebalance_date,
        fallback_symbols=top_symbols + [str(row.get("symbol", "")).upper() for row in exit_rows],
        max_symbols=watchlist_limit,
    )
    pool_expected_weights = _build_pool_expected_weights(
        pool_symbols=pool_symbols,
        target_rows=target_rows,
    )
    research_curve_symbols = list(pool_symbols or top_symbols)
    expert_symbols = _pick_expert_symbols_for_snapshot(
        pool_expected_weights=pool_expected_weights,
        fallback_symbols=top_symbols,
        limit=max(3, min(12, watchlist_limit)),
    )
    model_name_hint = _infer_model_name_hint(source_frame, strategy_id=strategy_id)
    expert_snapshot = _build_expert_snapshot(
        strategy_id=strategy_id,
        model_name_hint=model_name_hint,
        rebalance_date=rebalance_date,
        symbols=expert_symbols,
    )
    research_curve_lookback, expert_input_window, research_curve_rule = _resolve_research_curve_lookback(
        config=config,
        expert_snapshot=expert_snapshot,
    )
    research_curves = _build_symbol_price_curves(
        source_frame=market_curve_frame,
        symbols=research_curve_symbols,
        up_to_date=rebalance_date,
        lookback=research_curve_lookback,
    )
    current_distribution = _build_current_distribution(
        account_snapshot=account_snapshot,
        positions_snapshot=positions_snapshot,
    )
    equity_curve = _load_equity_curve(latest_state.get("ledger_path"))
    submit_curve_symbols = _select_submit_curve_symbols(
        positions_snapshot=positions_snapshot,
        top_symbols=top_symbols,
        max_count=4,
    )
    symbol_pnl_curves = _build_symbol_price_curves(
        source_frame=source_frame,
        symbols=submit_curve_symbols,
        up_to_date=rebalance_date,
        lookback=45,
    )
    if phase == "submit":
        expected_projection = {}
        expected_projection_reliable = False
    else:
        expected_projection = _build_expected_projection(
            source_frame=source_frame,
            top_positions=top_positions,
        )
        expected_projection_reliable = _normalize(expected_projection.get("model_quality")) == "ok"
        if not expected_projection_reliable:
            expected_projection = {}
    research_conclusion = _build_research_conclusion(
        top_positions=top_positions,
        expert_snapshot=expert_snapshot,
    )

    strategy_name_cn = _strategy_cn_name(strategy_id, fallback=str(config.get("description") or strategy_id))
    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_name_cn,
        "strategy_alias": strategy_name_cn,
        "config_path": str(config_path.resolve()),
        "phase": phase,
        "rebalance_date": rebalance_date,
        "description": str(config.get("description") or ""),
        "top_positions": top_positions,
        "exit_symbols": [str(row.get("symbol", "")).upper() for row in exit_rows[:5]],
        "positive_target_count": len(positive_targets),
        "exit_count": len(exit_rows),
        "action_counts": dict(Counter(_normalize(row.get("action")) for row in target_rows)),
        "order_status_counts": dict(Counter(_normalize(item.get("status")) for item in order_statuses)),
        "submitted_count": submitted_count,
        "open_order_count": open_order_count,
        "execution_state": execution_state,
        "distribution_source": distribution_source,
        "distribution_refresh": distribution_refresh,
        "order_settlement": settlement,
        "has_rejected_orders": bool(settlement.get("has_rejected")),
        "account": {"equity": account_equity, "cash": _coerce_float(account_snapshot.get("cash")), "buying_power": _coerce_float(latest_state.get("account_buying_power")) or _coerce_float(account_snapshot.get("buying_power")), "planning_equity": planning_equity, "buying_power_buffer": buffer, "currency": account_snapshot.get("currency") or "USD"},
        "alerts": alerts,
        "healthcheck_reasons": list(healthcheck.reasons) if phase == "submit" else [],
        "source_summary": _summarize_source_metrics(source_summary),
        "paths": {"source_path": str(resolved_source_path) if resolved_source_path else "", "summary_path": str(_resolve_path(source.get("summary_path") or latest_state.get("source_summary_path"))) if (source.get("summary_path") or latest_state.get("source_summary_path")) else "", "run_dir": str(_resolve_path(latest_state.get("run_dir"))) if latest_state.get("run_dir") else "", "latest_state_path": healthcheck.state_path},
        "latest_state": latest_state if phase == "submit" else {},
        "explain_like_human": _human_summary(
            phase,
            strategy_name_cn,
            top_positions[:3],
            [str(row.get("symbol", "")).upper() for row in exit_rows[:3]],
            submitted_count,
            open_order_count,
        ),
        "next_steps": _build_next_steps(phase, alerts, len(positive_targets), submitted_count, open_order_count),
        "beginner_notes": _build_beginner_notes(phase, {"cash": _coerce_float(account_snapshot.get("cash")), "buying_power": _coerce_float(latest_state.get("account_buying_power")) or _coerce_float(account_snapshot.get("buying_power"))}, open_order_count, len(positive_targets), submitted_count),
        "research_curves": research_curves,
        "expert_snapshot": expert_snapshot,
        "research_conclusion": research_conclusion,
        "analysis_pool_symbols": pool_symbols,
        "analysis_pool_source": pool_source,
        "analysis_curve_source": market_curve_source,
        "research_curve_lookback": research_curve_lookback,
        "expert_input_window": expert_input_window,
        "research_curve_rule": research_curve_rule,
        "pool_expected_weights": pool_expected_weights,
        "current_distribution": current_distribution,
        "equity_curve": equity_curve,
        "symbol_pnl_curves": symbol_pnl_curves,
        "expected_projection_reliable": expected_projection_reliable,
        "expected_projection": expected_projection,
    }


def _load_targets(*, source_path: str | Path | None, actions_path: str | Path | None, rebalance_selection: str) -> list[Any]:
    resolved_source = _resolve_path(source_path)
    if resolved_source is None or not resolved_source.exists():
        return []
    return load_target_positions(resolved_source, rebalance_selection, actions_path=_resolve_path(actions_path))


def _render_visual_artifacts(
    *,
    brief: Mapping[str, Any],
    run_dir: Path,
    dashboard_path: Path,
    html_path: Path,
) -> dict[str, Any]:
    try:
        return _render_operation_brief_html_page(
            brief=brief,
            run_dir=run_dir,
            html_path=html_path,
            dashboard_path=dashboard_path,
        )
    except Exception as exc:
        _render_operation_brief_poster(brief=brief, output_path=dashboard_path)
        html_path.write_text(_build_html(brief, dashboard_path.name), encoding="utf-8")
        return {"renderer": "poster_fallback", "error": str(exc)}


def _render_dashboard(brief: Mapping[str, Any], output_path: Path) -> None:
    _render_operation_brief_poster(brief=brief, output_path=output_path)


def _render_research_a4_poster(*, brief: Mapping[str, Any], output_path: Path) -> None:
    strategies = list(brief.get("strategies") or [])[:2]
    fig = plt.figure(figsize=A4_LANDSCAPE)
    fig.patch.set_facecolor("#f4efe6")
    grid = fig.add_gridspec(3, 1, height_ratios=[0.16, 0.42, 0.42], hspace=0.22)
    _draw_poster_header(fig=fig, brief=brief)

    for idx in range(2):
        area = grid[idx + 1].subgridspec(1, 3, width_ratios=[1.0, 1.25, 1.25], wspace=0.18)
        ax_left = fig.add_subplot(area[0, 0])
        ax_mid = fig.add_subplot(area[0, 1])
        ax_right = fig.add_subplot(area[0, 2])
        for panel in (ax_left, ax_mid, ax_right):
            _style_chart_panel(panel)
        if idx >= len(strategies):
            _draw_empty_strategy_panel(ax_left, ax_mid, ax_right)
            continue
        strategy = strategies[idx]
        _draw_allocation(ax_left, strategy)
        _draw_research_pool_curves(ax_mid, strategy)
        _draw_research_expert_snapshot(ax_right, strategy)

    fig.savefig(output_path, dpi=220, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def _render_submit_a4_poster(*, brief: Mapping[str, Any], output_path: Path) -> None:
    strategies = list(brief.get("strategies") or [])[:2]
    fig = plt.figure(figsize=A4_LANDSCAPE)
    fig.patch.set_facecolor("#f4efe6")
    grid = fig.add_gridspec(3, 1, height_ratios=[0.16, 0.42, 0.42], hspace=0.24)
    _draw_poster_header(fig=fig, brief=brief)

    for idx in range(2):
        area = grid[idx + 1].subgridspec(2, 3, width_ratios=[1.0, 1.2, 1.3], height_ratios=[1.0, 1.0], wspace=0.18, hspace=0.45)
        ax_dist = fig.add_subplot(area[:, 0])
        ax_total = fig.add_subplot(area[0, 1])
        ax_symbol = fig.add_subplot(area[1, 1])
        ax_projection = fig.add_subplot(area[:, 2])
        for panel in (ax_dist, ax_total, ax_symbol, ax_projection):
            _style_chart_panel(panel)
        if idx >= len(strategies):
            _draw_empty_submit_panel(ax_dist, ax_total, ax_symbol, ax_projection)
            continue
        strategy = strategies[idx]
        _draw_submit_current_distribution(ax_dist, strategy)
        _draw_submit_total_pnl_curve(ax_total, strategy)
        _draw_submit_symbol_pnl_curves(ax_symbol, strategy)
        _draw_submit_expected_projection(ax_projection, strategy)

    fig.savefig(output_path, dpi=220, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def _draw_poster_header(*, fig: Any, brief: Mapping[str, Any]) -> None:
    summary = dict(brief.get("summary") or {})
    status_style = STATUS_STYLES.get(str(brief.get("status") or "success"), STATUS_STYLES["success"])
    display_title = _brief_display_title(brief)
    generated_at = _format_generated_time_cn(str(brief.get("generated_at_utc") or "")) or str(brief.get("generated_at_utc") or "")

    fig.text(0.5, 0.968, display_title, ha="center", va="center", fontsize=22, fontweight="bold", color="#0f172a")
    fig.text(
        0.5,
        0.934,
        " | ".join(
            [
                f"状态 {STATUS_STYLES.get(str(brief.get('status')), STATUS_STYLES['success'])['label']}",
                f"北京时间 {generated_at}",
                f"策略 {summary.get('strategy_count', 0)}",
                f"目标仓位 {summary.get('positive_target_count', 0)}",
                f"已提单 {summary.get('submitted_count', 0)}",
                f"未完成 {summary.get('open_order_count', 0)}",
            ]
        ),
        ha="center",
        va="center",
        fontsize=9.8,
        color="#475569",
    )
    fig.text(
        0.04,
        0.968,
        f"  {status_style['label']}  ",
        ha="left",
        va="center",
        fontsize=9.5,
        color=status_style["color"],
        bbox={"boxstyle": "round,pad=0.3", "facecolor": status_style["background"], "edgecolor": status_style["background"]},
    )


def _style_chart_panel(ax: Any) -> None:
    ax.set_facecolor("#fffdf8")
    for spine in ax.spines.values():
        spine.set_color("#d6dde5")
        spine.set_linewidth(0.9)


def _draw_empty_strategy_panel(ax_left: Any, ax_mid: Any, ax_right: Any) -> None:
    for ax in (ax_left, ax_mid, ax_right):
        ax.axis("off")
        ax.text(0.5, 0.5, "无策略数据", ha="center", va="center", fontsize=12, color="#64748b")


def _draw_empty_submit_panel(ax_dist: Any, ax_total: Any, ax_symbol: Any, ax_projection: Any) -> None:
    for ax in (ax_dist, ax_total, ax_symbol, ax_projection):
        ax.axis("off")
        ax.text(0.5, 0.5, "无策略数据", ha="center", va="center", fontsize=12, color="#64748b")


def _annotate_strategy_footer(ax: Any, strategy: Mapping[str, Any]) -> None:
    top_text = _top_positions_text(list(strategy.get("top_positions") or []), limit=3)
    explain = str(strategy.get("explain_like_human") or "")
    footer = f"重点仓位：{top_text}\n{explain[:88]}"
    ax.text(
        0.01,
        -0.22,
        footer,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8.2,
        color="#334155",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#f8fafc", "edgecolor": "#e2e8f0"},
    )


def _draw_allocation(ax: Any, strategy: Mapping[str, Any]) -> None:
    top_positions = list(strategy.get("top_positions") or [])
    if not top_positions:
        ax.axis("off")
        ax.text(0.5, 0.5, "暂无目标仓位", ha="center", va="center", fontsize=12, color="#52606d")
        return
    labels = [str(item.get("symbol", "")) for item in top_positions]
    weights = [_coerce_float(item.get("target_weight")) or 0.0 for item in top_positions]
    remainder = max(0.0, 1.0 - sum(weights))
    if remainder > 0.001:
        labels.append("现金/其他")
        weights.append(remainder)
    ax.pie(weights, labels=labels, colors=PIE_COLORS[: len(weights)], startangle=120, autopct=lambda pct: f"{pct:.1f}%" if pct > 4 else "", wedgeprops={"width": 0.45, "edgecolor": "#ffffff"}, textprops={"fontsize": 9, "color": "#102a43"})
    ax.set_title(f"{_strategy_chart_title(strategy)}\n目标仓位分布", fontsize=11, fontweight="bold", color="#102a43", pad=10)
    ax.text(0.0, -1.22, _chart_summary(strategy), ha="center", va="center", fontsize=9, color="#334e68", wrap=True, transform=ax.transData)


def _draw_activity(ax: Any, strategy: Mapping[str, Any]) -> None:
    counts = dict(strategy.get("order_status_counts") or {}) if strategy.get("phase") == "submit" and strategy.get("order_status_counts") else dict(strategy.get("action_counts") or {})
    title = "券商订单状态" if strategy.get("phase") == "submit" and strategy.get("order_status_counts") else "动作分布"
    if counts:
        keys = list(counts.keys())
        labels = [ACTION_LABELS.get(key, str(key).title()) for key in keys]
        values = [int(counts[key]) for key in keys]
        ax.bar(labels, values, color=BAR_COLORS[: len(values)], width=0.6)
        upper = max(values) * 1.35 if values else 1.0
        ax.set_ylim(0, max(1.0, upper))
        for idx, value in enumerate(values):
            ax.text(idx, value + max(0.08, upper * 0.03), str(value), ha="center", va="bottom", fontsize=9)
    else:
        ax.text(0.5, 0.5, "暂无活动数据", ha="center", va="center", fontsize=12, color="#52606d")
    ax.set_title(f"{strategy.get('strategy_id', '')}\n{title}", fontsize=12, fontweight="bold", color="#102a43", pad=12)
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.02, 0.98, _metrics_text(strategy), transform=ax.transAxes, ha="left", va="top", fontsize=9, color="#102a43", bbox={"boxstyle": "round,pad=0.45", "facecolor": "#fffdf8", "edgecolor": "#d9e2ec"})


def _draw_research_pool_curves(ax: Any, strategy: Mapping[str, Any]) -> None:
    curves = dict(strategy.get("research_curves") or {})
    if not curves:
        ax.text(0.5, 0.5, "暂无股票池曲线数据", ha="center", va="center", fontsize=12, color="#52606d")
        ax.set_axis_off()
        return
    for symbol, points in curves.items():
        points_list = list(points) if isinstance(points, Sequence) else []
        if not points_list:
            continue
        ys = [(_coerce_float(item.get("normalized_close")) or 1.0) * 100.0 for item in points_list if isinstance(item, Mapping)]
        if not ys:
            continue
        xs = list(range(len(ys)))
        ax.plot(xs, ys, linewidth=2.0, label=str(symbol))
    ax.set_title(f"{_strategy_chart_title(strategy)}\n目标股票池价格曲线（归一化）", fontsize=11, fontweight="bold", color="#102a43", pad=10)
    ax.set_ylabel("价格指数 (首日=100)", color="#334e68")
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    conclusion = str(strategy.get("research_conclusion") or "")
    if conclusion:
        ax.text(
            0.02,
            0.02,
            f"结论：{conclusion}",
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.5,
            color="#102a43",
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "#fffdf8", "edgecolor": "#d9e2ec"},
        )


def _draw_research_expert_snapshot(ax: Any, strategy: Mapping[str, Any]) -> None:
    snapshot = dict(strategy.get("expert_snapshot") or {})
    symbols = [str(item) for item in list(snapshot.get("symbols") or []) if str(item).strip()]
    experts = [str(item) for item in list(snapshot.get("experts") or []) if str(item).strip()]
    score_map = snapshot.get("scores")
    if not symbols or not experts or not isinstance(score_map, Mapping):
        ax.text(0.5, 0.5, "暂无 expert/voting 预测快照", ha="center", va="center", fontsize=12, color="#52606d")
        ax.set_axis_off()
        return

    width = max(0.12, 0.78 / max(1, len(experts)))
    x_base = list(range(len(symbols)))
    has_value = False
    for index, expert in enumerate(experts):
        expert_values = score_map.get(expert) if isinstance(score_map.get(expert), Mapping) else {}
        values = []
        for symbol in symbols:
            value = _coerce_float(expert_values.get(symbol))
            if value is None:
                values.append(0.0)
            else:
                values.append(value)
                has_value = True
        offset = (index - (len(experts) - 1) / 2.0) * width
        xs = [item + offset for item in x_base]
        ax.bar(xs, values, width=width * 0.9, label=_display_expert_name(expert))
    if not has_value:
        ax.text(0.5, 0.5, "专家预测为空", ha="center", va="center", fontsize=12, color="#52606d")
        ax.set_axis_off()
        return
    ax.set_xticks(x_base)
    ax.set_xticklabels(symbols, fontsize=8)
    ax.set_title(f"{_strategy_chart_title(strategy)}\n五专家与 Voting 预测对比", fontsize=11, fontweight="bold", color="#102a43", pad=10)
    ax.set_ylabel("模型信号值", color="#334e68")
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", fontsize=7.5, ncol=3)
    asof = str(snapshot.get("asof_date") or "")
    if asof:
        ax.text(
            0.02,
            0.96,
            f"快照日期：{asof}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8,
            color="#52606d",
        )


def _draw_submit_current_distribution(ax: Any, strategy: Mapping[str, Any]) -> None:
    distribution = [dict(item) for item in list(strategy.get("current_distribution") or []) if isinstance(item, Mapping)]
    if not distribution:
        ax.text(0.5, 0.5, "暂无当前仓位分布", ha="center", va="center", fontsize=12, color="#52606d")
        ax.set_axis_off()
        return
    labels = [str(item.get("label", "")) for item in distribution]
    values = [max(0.0, _coerce_float(item.get("value")) or 0.0) for item in distribution]
    total = sum(values)
    if total <= 0:
        ax.text(0.5, 0.5, "仓位金额为空", ha="center", va="center", fontsize=12, color="#52606d")
        ax.set_axis_off()
        return
    ax.pie(
        values,
        labels=labels,
        colors=PIE_COLORS[: len(values)],
        startangle=120,
        autopct=lambda pct: f"{pct:.1f}%" if pct > 4 else "",
        wedgeprops={"width": 0.45, "edgecolor": "#ffffff"},
        textprops={"fontsize": 8.5, "color": "#102a43"},
    )
    ax.set_title(f"{_strategy_chart_title(strategy)}\n当前仓位分布", fontsize=10, fontweight="bold", color="#102a43", pad=8)
    ax.text(
        0.0,
        -1.22,
        f"总金额：{total:,.0f} {strategy.get('account', {}).get('currency', 'USD')}",
        ha="center",
        va="center",
        fontsize=9,
        color="#334e68",
        transform=ax.transData,
    )


def _draw_submit_total_pnl_curve(ax: Any, strategy: Mapping[str, Any]) -> None:
    curve = [dict(item) for item in list(strategy.get("equity_curve") or []) if isinstance(item, Mapping)]
    if len(curve) < 2:
        top_positions = list(strategy.get("top_positions") or [])
        if not top_positions:
            ax.text(0.5, 0.5, "权益曲线样本不足", ha="center", va="center", fontsize=12, color="#52606d")
            ax.set_axis_off()
            return
        symbols = [str(item.get("symbol", "")).upper() for item in top_positions[:5]]
        values = [((_coerce_float(item.get("target_weight")) or 0.0) * 100.0) for item in top_positions[:5]]
        ax.bar(symbols, values, color=BAR_COLORS[: len(values)], alpha=0.9)
        for idx, value in enumerate(values):
            ax.text(idx, value + 0.6, f"{value:.1f}%", ha="center", va="bottom", fontsize=8.5, color="#334e68")
        ax.set_title(f"{_strategy_chart_title(strategy)}\n目标权重快照（权益曲线不足）", fontsize=10, fontweight="bold", color="#102a43", pad=8)
        ax.set_ylabel("目标权重 (%)", color="#334e68")
        ax.grid(axis="y", color="#d9e2ec", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        return
    xs = list(range(len(curve)))
    ys = [(_coerce_float(item.get("pnl_pct")) or 0.0) * 100.0 for item in curve]
    if max(abs(item) for item in ys) < 0.01:
        ys = [0.0 for _ in ys]
    ax.plot(xs, ys, color="#1d3557", linewidth=2.2, marker="o", markersize=3)
    ax.axhline(0.0, color="#9aa5b1", linewidth=1.0, linestyle="--")
    ax.fill_between(xs, ys, 0.0, color="#a8dadc", alpha=0.25)
    ax.set_title(f"{_strategy_chart_title(strategy)}\n总仓盈亏曲线", fontsize=10, fontweight="bold", color="#102a43", pad=8)
    ax.set_ylabel("累计收益 (%)", color="#334e68")
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    first_date = str(curve[0].get("date") or "")
    last_date = str(curve[-1].get("date") or "")
    ax.text(0.02, 0.95, f"{first_date} → {last_date}", transform=ax.transAxes, ha="left", va="top", fontsize=8.5, color="#52606d")


def _has_plottable_symbol_curves(strategy: Mapping[str, Any]) -> bool:
    curves = dict(strategy.get("symbol_pnl_curves") or {})
    for points in curves.values():
        points_list = list(points) if isinstance(points, Sequence) else []
        if len(points_list) >= 2:
            return True
    return False


def _draw_submit_symbol_proxy(ax: Any, strategy: Mapping[str, Any]) -> None:
    top_positions = [dict(item) for item in list(strategy.get("top_positions") or []) if isinstance(item, Mapping)]
    if not top_positions:
        ax.text(0.5, 0.5, "暂无单股波动数据", ha="center", va="center", fontsize=11, color="#52606d")
        ax.set_axis_off()
        return
    symbols = [str(item.get("symbol", "")).upper() for item in top_positions[:5]]
    scores = [(_coerce_float(item.get("score")) or 0.0) for item in top_positions[:5]]
    ax.bar(symbols, scores, color=BAR_COLORS[: len(symbols)], alpha=0.9)
    ax.axhline(0.0, color="#9aa5b1", linewidth=1.0, linestyle="--")
    for idx, value in enumerate(scores):
        ax.text(idx, value + (0.02 if value >= 0 else -0.02), f"{value:.2f}", ha="center", va=("bottom" if value >= 0 else "top"), fontsize=8)
    ax.set_title(f"{_strategy_chart_title(strategy)}\n单股信号强弱（曲线缺失）", fontsize=10, fontweight="bold", color="#102a43", pad=8)
    ax.set_ylabel("模型信号", color="#334e68")
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _draw_submit_symbol_pnl_curves(ax: Any, strategy: Mapping[str, Any]) -> None:
    curves = dict(strategy.get("symbol_pnl_curves") or {})
    if not curves:
        _draw_submit_symbol_proxy(ax, strategy)
        return
    plotted = 0
    for symbol, points in curves.items():
        points_list = list(points) if isinstance(points, Sequence) else []
        ys = [(_coerce_float(item.get("return_pct")) or 0.0) * 100.0 for item in points_list if isinstance(item, Mapping)]
        if len(ys) < 2:
            continue
        xs = list(range(len(ys)))
        ax.plot(xs, ys, linewidth=1.9, label=str(symbol))
        plotted += 1
    if plotted == 0:
        _draw_submit_symbol_proxy(ax, strategy)
        return
    ax.axhline(0.0, color="#9aa5b1", linewidth=1.0, linestyle="--")
    ax.set_title(f"{_strategy_chart_title(strategy)}\n单股盈亏曲线（代理）", fontsize=10, fontweight="bold", color="#102a43", pad=8)
    ax.set_ylabel("累计收益 (%)", color="#334e68")
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.text(0.02, 0.02, "说明：以持仓标的价格收益近似单股盈亏轨迹。", transform=ax.transAxes, ha="left", va="bottom", fontsize=8, color="#52606d")


def _draw_submit_expected_projection(ax: Any, strategy: Mapping[str, Any]) -> None:
    projection = dict(strategy.get("expected_projection") or {})
    contributions = [dict(item) for item in list(projection.get("contributions") or []) if isinstance(item, Mapping)]
    trend_curve = [dict(item) for item in list(projection.get("trend_curve") or []) if isinstance(item, Mapping)]
    if not contributions and not trend_curve:
        ax.text(0.5, 0.5, "暂无下单后趋势估计", ha="center", va="center", fontsize=12, color="#52606d")
        ax.set_axis_off()
        return

    if contributions:
        symbols = [str(item.get("symbol", "")) for item in contributions]
        values = [(_coerce_float(item.get("contribution")) or 0.0) * 100.0 for item in contributions]
        ax.bar(symbols, values, color=BAR_COLORS[: len(values)], alpha=0.92)
        ax.axhline(0.0, color="#9aa5b1", linewidth=1.0, linestyle="--")
        for idx, value in enumerate(values):
            ax.text(idx, value + (0.06 if value >= 0 else -0.06), f"{value:.2f}%", ha="center", va=("bottom" if value >= 0 else "top"), fontsize=8)
    ax.set_title(f"{_strategy_chart_title(strategy)}\n下单后预计盈亏趋势", fontsize=10, fontweight="bold", color="#102a43", pad=8)
    ax.set_ylabel("5日贡献(%)", color="#334e68")
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if trend_curve:
        ax2 = ax.twinx()
        xs = [int(_coerce_float(item.get("day")) or 0) for item in trend_curve]
        ys = [(_coerce_float(item.get("portfolio_return")) or 0.0) * 100.0 for item in trend_curve]
        ax2.plot(xs, ys, color="#0b6e4f", linewidth=2.0, marker="o", markersize=3)
        ax2.set_ylabel("组合趋势(%)", color="#0b6e4f")
        ax2.tick_params(axis="y", labelcolor="#0b6e4f")
        ax2.grid(False)
    expected_total = (_coerce_float(projection.get("expected_portfolio_return")) or 0.0) * 100.0
    ax.text(
        0.02,
        0.95,
        f"预计5日组合收益：{expected_total:.2f}%",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        color="#102a43",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#fffdf8", "edgecolor": "#d9e2ec"},
    )


def _display_expert_name(name: str) -> str:
    mapping = {
        "lightgbm": "LightGBM",
        "xgboost": "XGBoost",
        "catboost": "CatBoost",
        "lstm": "LSTM",
        "transformer": "Transformer",
        "ensemble": "Voting",
    }
    normalized = _normalize(name)
    return mapping.get(normalized, name)


def _strategy_chart_title(strategy: Mapping[str, Any]) -> str:
    full = _strategy_panel_title(strategy)
    if "A股训练零样本" in full:
        return "A股零样本策略"
    if "美股全量训练" in full:
        return "美股全量策略"
    return full if len(full) <= 14 else (full[:13] + "…")


def _strategy_panel_title(strategy: Mapping[str, Any]) -> str:
    alias = str(strategy.get("strategy_alias") or strategy.get("strategy_name") or "").strip()
    if alias:
        return alias
    return _strategy_cn_name(str(strategy.get("strategy_id") or ""), fallback=str(strategy.get("strategy_id") or ""))


def _brief_display_title(brief: Mapping[str, Any]) -> str:
    title = str(brief.get("title") or "").strip()
    if _has_cjk(title):
        return title
    phase = str(brief.get("phase") or "").strip()
    return PHASE_TITLES.get(phase, title or "运行简报")


def _has_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in str(value))


def _build_markdown(brief: Mapping[str, Any], dashboard_name: str) -> str:
    phase_label = PHASE_LABELS.get(str(brief.get("phase", "")), str(brief.get("phase", "")))
    generated_at_cn = _format_generated_time_cn(str(brief.get("generated_at_utc") or "")) or str(brief.get("generated_at_utc") or "")
    display_title = _brief_display_title(brief)
    lines = [f"# {display_title}", "", f"- 阶段：`{phase_label}`", f"- 状态：`{brief.get('status_display', '')}`", f"- 生成时间：`北京时间 {generated_at_cn}`", "", f"![简报面板]({dashboard_name})", ""]
    for strategy in brief.get("strategies", []):
        strategy_title = _strategy_panel_title(strategy)
        lines.extend([f"## {strategy_title}", "", str(strategy.get("explain_like_human") or ""), "", f"- 调仓日期：`{strategy.get('rebalance_date') or 'n/a'}`", f"- 目标仓位数：`{strategy.get('positive_target_count', 0)}`", f"- 退出标的：`{', '.join(strategy.get('exit_symbols', [])) or 'n/a'}`", f"- 已提交订单：`{strategy.get('submitted_count', 0)}`", f"- 未完成挂单：`{strategy.get('open_order_count', 0)}`", "", "| 股票 | 权重 | 计划金额 | 行业 |", "| --- | ---: | ---: | --- |"])
        for item in strategy.get("top_positions", []):
            lines.append("| {symbol} | {weight:.1f}% | {notional} | {industry} |".format(symbol=item.get("symbol", ""), weight=(_coerce_float(item.get("target_weight")) or 0.0) * 100, notional=(f"{(_coerce_float(item.get('planned_notional')) or 0.0):,.0f}" if _coerce_float(item.get("planned_notional")) is not None else "n/a"), industry=item.get("industry_group", "") or "-"))
        lines.extend(["", "下一步建议："])
        lines.extend(f"- {step}" for step in strategy.get("next_steps", []))
        lines.extend(["", "新手说明："])
        lines.extend(f"- {note}" for note in strategy.get("beginner_notes", []))
        if strategy.get("alerts"):
            lines.extend(["", "告警："])
            lines.extend(f"- [{ALERT_SEVERITY_LABELS.get(str(alert.get('severity', 'info')), str(alert.get('severity', 'info')))}] {alert.get('title', '')}: {alert.get('message', '')}" for alert in strategy.get("alerts", []))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_html(brief: Mapping[str, Any], dashboard_name: str) -> str:
    summary = dict(brief.get("summary") or {})
    status_style = STATUS_STYLES.get(str(brief.get("status")), STATUS_STYLES["success"])
    generated_at_cn = _format_generated_time_cn(str(brief.get("generated_at_utc") or "")) or str(brief.get("generated_at_utc") or "")
    display_title = _brief_display_title(brief)
    cards = "".join(f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>' for label, value in (("策略数", summary.get("strategy_count", 0)), ("目标仓位", summary.get("positive_target_count", 0)), ("已提订单", summary.get("submitted_count", 0)), ("未完成挂单", summary.get("open_order_count", 0))))
    sections = []
    for strategy in brief.get("strategies", []):
        strategy_title = _strategy_panel_title(strategy)
        rows = "".join("<tr><td>{symbol}</td><td>{weight:.1f}%</td><td>{industry}</td><td>{notional}</td></tr>".format(symbol=item.get("symbol", ""), weight=(_coerce_float(item.get("target_weight")) or 0.0) * 100, industry=item.get("industry_group", "") or "-", notional=(f"{(_coerce_float(item.get('planned_notional')) or 0.0):,.0f}" if _coerce_float(item.get("planned_notional")) is not None else "n/a")) for item in strategy.get("top_positions", []))
        badges = "".join(f'<span class="badge {str(alert.get("severity", "info"))}">{alert.get("title", alert.get("code", ""))}</span>' for alert in strategy.get("alerts", [])) or '<span class="badge info">当前无告警</span>'
        next_steps = "".join(f"<li>{step}</li>" for step in strategy.get("next_steps", []))
        beginner_notes = "".join(f"<li>{note}</li>" for note in strategy.get("beginner_notes", []))
        sections.append(f'<section class="section"><h2>{strategy_title}</h2><p class="summary">{strategy.get("explain_like_human", "")}</p><div class="meta"><span>调仓日期：{strategy.get("rebalance_date") or "n/a"}</span><span>目标仓位：{strategy.get("positive_target_count", 0)}</span><span>退出标的：{strategy.get("exit_count", 0)}</span><span>已提订单：{strategy.get("submitted_count", 0)}</span><span>未完成挂单：{strategy.get("open_order_count", 0)}</span></div><div class="badges">{badges}</div><table><thead><tr><th>股票</th><th>权重</th><th>行业</th><th>计划金额</th></tr></thead><tbody>{rows}</tbody></table><div class="notes-grid"><div><h3>下一步建议</h3><ul>{next_steps}</ul></div><div><h3>新手说明</h3><ul>{beginner_notes}</ul></div></div></section>')
    return f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{display_title}</title><style>body{{margin:0;padding:32px;background:linear-gradient(180deg,#f7f3eb,#fffdf9);color:#102a43;font-family:"Microsoft YaHei","PingFang SC",sans-serif;}}.hero,.section{{max-width:1120px;margin:0 auto 20px auto;background:rgba(255,255,255,0.9);border:1px solid #eadfce;border-radius:20px;padding:24px 28px;box-shadow:0 12px 34px rgba(31,41,51,0.06);}}h1{{margin:0 0 8px 0;font-size:34px;}}h2{{margin:0 0 8px 0;font-size:24px;}}h3{{margin:0 0 8px 0;font-size:16px;}}.sub,.summary{{color:#52606d;}}.status-badge{{display:inline-block;padding:8px 12px;border-radius:999px;font-weight:700;color:{status_style["color"]};background:{status_style["background"]};}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:14px;margin:18px 0;}}.card{{background:#fffdf8;border:1px solid #eadfce;border-radius:16px;padding:14px 16px;}}.label{{font-size:12px;letter-spacing:.08em;color:#7b8794;}}.value{{font-size:28px;font-weight:700;margin-top:8px;}}.dashboard img{{width:100%;border-radius:16px;border:1px solid #eadfce;}}.meta,.badges{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 12px 0;}}.meta span,.badge{{background:#f8f4ec;border:1px solid #eadfce;border-radius:999px;padding:6px 10px;font-size:13px;}}.badge.warning{{background:#fff2d8;color:#9c6500;}}.badge.critical{{background:#fde4e1;color:#9b1c1c;}}table{{width:100%;border-collapse:collapse;background:#fffdf8;border-radius:14px;overflow:hidden;}}th,td{{padding:12px 14px;border-bottom:1px solid #f0e6d6;text-align:left;font-size:14px;}}th{{font-size:12px;letter-spacing:.08em;color:#52606d;background:#fbf7f0;}}tbody tr:last-child td{{border-bottom:none;}}.notes-grid{{display:grid;grid-template-columns:repeat(2,minmax(240px,1fr));gap:18px;margin-top:18px;}}ul{{margin:0;padding-left:20px;color:#334e68;}}</style></head><body><div class="hero"><h1>{display_title}</h1><div class="sub"><span class="status-badge">{brief.get("status_display", "")}</span> 生成时间 {generated_at_cn}（北京时间）</div><div class="cards">{cards}</div><div class="dashboard"><img src="{dashboard_name}" alt="简报面板"></div></div>{"".join(sections)}</body></html>'


def _maybe_send_notifications(
    *,
    brief: Mapping[str, Any],
    run_dir: Path,
    html_path: Path,
    dashboard_path: Path,
) -> dict[str, Any]:
    config = _load_json_mapping(DEFAULT_NOTIFICATION_CONFIG)
    feishu = dict(config.get("feishu") or {})
    if feishu and not bool(feishu.get("enabled", True)):
        return {"enabled": False, "reason": "feishu_disabled"}
    webhook_url = str(feishu.get("webhook_url") or os.environ.get("QSF_FEISHU_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return {"enabled": False, "reason": "feishu_webhook_missing"}

    if str(brief.get("phase") or "") == "submit":
        submit_policy = _resolve_submit_notification_policy(config=config, feishu=feishu)
        execution_state = str(brief.get("execution_state") or "final")
        if not _submit_notification_policy_allows(submit_policy, execution_state):
            return {
                "enabled": True,
                "channel": "feishu",
                "sent": False,
                "reason": f"submit_policy_blocked:{submit_policy}:{execution_state}",
                "submit_policy": submit_policy,
                "execution_state": execution_state,
            }

    image_upload = _maybe_upload_feishu_dashboard_image(feishu=feishu, dashboard_path=dashboard_path)
    payload = build_feishu_post_payload(
        brief=brief,
        run_dir=run_dir,
        html_path=html_path,
        image_key=str(image_upload.get("image_key", "")),
    )
    secret = str(feishu.get("secret") or os.environ.get("QSF_FEISHU_WEBHOOK_SECRET") or "").strip()
    if secret:
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        payload["timestamp"] = timestamp
        payload["sign"] = _build_feishu_signature(timestamp=timestamp, secret=secret)
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        body = response.json() if response.content else {}
    except Exception as exc:
        return {
            "enabled": True,
            "channel": "feishu",
            "sent": False,
            "error": str(exc),
            "image_upload": image_upload,
        }
    return {
        "enabled": True,
        "channel": "feishu",
        "sent": bool(body.get("code", 0) == 0),
        "response": body,
        "image_upload": image_upload,
    }


def _resolve_submit_notification_policy(*, config: Mapping[str, Any], feishu: Mapping[str, Any]) -> str:
    candidates = [
        feishu.get("submit_brief_policy"),
        feishu.get("submit_policy"),
        config.get("submit_brief_policy"),
        config.get("submit_policy"),
        os.environ.get("QSF_FEISHU_SUBMIT_BRIEF_POLICY"),
        os.environ.get("QSF_SUBMIT_BRIEF_POLICY"),
    ]
    for candidate in candidates:
        normalized = _normalize(candidate)
        if normalized:
            if normalized in {"final", "final_only", "settled", "complete"}:
                return "final_only"
            if normalized in {"provisional", "timeout", "timeout_only", "provisional_ok", "timeout_ok", "all", "any"}:
                return normalized
            return normalized
    return "final_only"


def _submit_notification_policy_allows(policy: str, execution_state: str) -> bool:
    policy = _normalize(policy) or "final_only"
    execution_state = _normalize(execution_state) or "final"
    if policy in {"final", "final_only", "settled", "complete"}:
        return execution_state == "final"
    if policy in {"provisional", "timeout", "timeout_only", "provisional_ok", "timeout_ok", "all", "any"}:
        return execution_state in {"final", "provisional"}
    return execution_state == "final"


def build_feishu_post_payload(
    brief: Mapping[str, Any],
    run_dir: Path,
    html_path: Path,
    image_key: str = "",
) -> dict[str, Any]:
    summary = dict(brief.get("summary") or {})
    display_title = _brief_display_title(brief)
    phase = str(brief.get("phase") or "")
    generated_at_cn = _format_generated_time_cn(str(brief.get("generated_at_utc") or "")) or str(brief.get("generated_at_utc") or "")
    content: list[list[dict[str, Any]]] = []
    if image_key:
        content.append(
            [
                {
                    "tag": "img",
                    "image_key": image_key,
                    "alt": {"tag": "plain_text", "content": "简报面板"},
                }
            ]
        )
    content.append([{"tag": "text", "text": f"状态：{brief.get('status_display', '')}  |  北京时间：{generated_at_cn}"}])
    content.append(
        [
            {
                "tag": "text",
                "text": "总览：策略 {strategy_count} 个，目标仓位 {targets} 个，已提订单 {submitted} 笔，未完成挂单 {open_orders} 笔".format(
                    strategy_count=summary.get("strategy_count", 0),
                    targets=summary.get("positive_target_count", 0),
                    submitted=summary.get("submitted_count", 0),
                    open_orders=summary.get("open_order_count", 0),
                ),
            }
        ]
    )
    if brief.get("notes"):
        content.append([{"tag": "text", "text": "备注：" + "；".join(str(note) for note in brief.get("notes", []))}])
    for strategy in brief.get("strategies", []):
        strategy_id = str(strategy.get("strategy_id", "")).strip()
        strategy_title = _strategy_cn_name(strategy_id, fallback=str(strategy.get("strategy_name") or strategy_id))
        top_positions = _top_positions_text(list(strategy.get("top_positions") or []), limit=3)
        alert_titles = "，".join(str(alert.get("title", alert.get("code", ""))) for alert in list(strategy.get("alerts") or [])[:2]) or "当前无告警"
        if phase == "research":
            agreement = (_coerce_float((strategy.get("expert_snapshot") or {}).get("agreement_ratio")) or 0.0) * 100.0
            conclusion = str(strategy.get("research_conclusion") or strategy.get("explain_like_human") or "暂无结论")
            content.extend(
                [
                    [{"tag": "text", "text": f"【{strategy_title}】"}],
                    [{"tag": "text", "text": f"重点仓位：{top_positions}"}],
                    [{"tag": "text", "text": f"专家一致性：{agreement:.0f}%"}],
                    [{"tag": "text", "text": f"结论：{conclusion}"}],
                ]
            )
        else:
            content.extend(
                [
                    [{"tag": "text", "text": f"【{strategy_title}】"}],
                    [{"tag": "text", "text": f"调仓：{strategy.get('rebalance_date') or 'n/a'} | 已提订单：{strategy.get('submitted_count', 0)} | 未完成：{strategy.get('open_order_count', 0)}"}],
                    [{"tag": "text", "text": f"重点仓位：{top_positions}"}],
                    [{"tag": "text", "text": f"提示：{alert_titles}"}],
                ]
            )
    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": display_title,
                    "content": content,
                }
            }
        },
    }


def _maybe_upload_feishu_dashboard_image(*, feishu: Mapping[str, Any], dashboard_path: Path) -> dict[str, Any]:
    if not bool(feishu.get("upload_dashboard_image", True)):
        return {"enabled": False, "reason": "upload_dashboard_image_disabled"}

    app_id = str(feishu.get("app_id") or os.environ.get("QSF_FEISHU_APP_ID") or "").strip()
    app_secret = str(feishu.get("app_secret") or os.environ.get("QSF_FEISHU_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        return {"enabled": False, "reason": "feishu_app_credentials_missing"}

    if not dashboard_path.exists():
        return {"enabled": True, "uploaded": False, "reason": "dashboard_png_missing"}

    try:
        image_key = _upload_feishu_image(
            image_path=dashboard_path,
            app_id=app_id,
            app_secret=app_secret,
        )
    except Exception as exc:
        return {
            "enabled": True,
            "uploaded": False,
            "reason": "image_upload_failed",
            "error": str(exc),
        }
    return {
        "enabled": True,
        "uploaded": True,
        "image_key": image_key,
    }


def _upload_feishu_image(*, image_path: Path, app_id: str, app_secret: str) -> str:
    token = _fetch_feishu_tenant_access_token(app_id=app_id, app_secret=app_secret)
    with image_path.open("rb") as handle:
        response = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            data={"image_type": "message"},
            files={"image": (image_path.name, handle, "application/octet-stream")},
            timeout=20,
        )
    response.raise_for_status()
    payload = response.json() if response.content else {}
    if int(payload.get("code", -1)) != 0:
        message = str(payload.get("msg") or "unknown_error")
        raise RuntimeError(f"Feishu image upload failed: {message}")
    data = payload.get("data") if isinstance(payload.get("data"), Mapping) else {}
    image_key = str(data.get("image_key") or "").strip()
    if not image_key:
        raise RuntimeError("Feishu image upload returned empty image_key")
    return image_key


def _fetch_feishu_tenant_access_token(*, app_id: str, app_secret: str) -> str:
    response = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={
            "app_id": app_id,
            "app_secret": app_secret,
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json() if response.content else {}
    if int(payload.get("code", -1)) != 0:
        message = str(payload.get("msg") or "unknown_error")
        raise RuntimeError(f"Fetch tenant_access_token failed: {message}")
    token = str(payload.get("tenant_access_token") or "").strip()
    if not token:
        raise RuntimeError("tenant_access_token is empty")
    return token


def _decorate_target(row: Mapping[str, Any], planning_equity: float | None) -> dict[str, Any]:
    metadata = _parse_metadata(row.get("metadata"))
    weight = _coerce_float(row.get("target_weight")) or 0.0
    return {**dict(row), "metadata": metadata, "industry_group": str(metadata.get("industry_group", "") or ""), "planned_notional": (None if planning_equity in (None, 0.0) else weight * float(planning_equity))}


def _metrics_text(strategy: Mapping[str, Any]) -> str:
    account = dict(strategy.get("account") or {})
    summary = dict(strategy.get("source_summary") or {})
    lines = [f"调仓日期：{strategy.get('rebalance_date') or 'n/a'}", f"目标仓位：做多 {int(strategy.get('positive_target_count', 0))} 个 / 退出 {int(strategy.get('exit_count', 0))} 个"]
    if account.get("equity"):
        lines.append(f"账户权益：{account.get('equity', 0.0):,.0f} {account.get('currency', 'USD')}")
    if account.get("cash") is not None:
        lines.append(f"现金：{float(account.get('cash') or 0.0):,.0f} {account.get('currency', 'USD')}")
    if account.get("buying_power") is not None:
        lines.append(f"可用购买力：{float(account.get('buying_power') or 0.0):,.0f}")
    if account.get("planning_equity") is not None:
        lines.append(f"计划投入资金：{float(account.get('planning_equity') or 0.0):,.0f}")
    if summary.get("annualized_return") is not None:
        lines.append(f"年化收益：{float(summary.get('annualized_return') or 0.0) * 100:.1f}%")
    if summary.get("win_rate") is not None:
        lines.append(f"胜率：{float(summary.get('win_rate') or 0.0) * 100:.1f}%")
    if strategy.get("alerts"):
        lines.append("告警代码：" + "，".join(str(alert.get("code", "")) for alert in strategy.get("alerts", [])[:3]))
    return "\n".join(lines)


def _build_summary(strategies: Sequence[Mapping[str, Any]], *, phase: str, status: str) -> dict[str, Any]:
    return {"phase": phase, "status": status, "strategy_count": len(strategies), "positive_target_count": sum(int(item.get("positive_target_count", 0)) for item in strategies), "exit_count": sum(int(item.get("exit_count", 0)) for item in strategies), "submitted_count": sum(int(item.get("submitted_count", 0)) for item in strategies), "open_order_count": sum(int(item.get("open_order_count", 0)) for item in strategies), "alert_counts": dict(Counter(str(alert.get("severity", "info")) for strategy in strategies for alert in strategy.get("alerts", []) if isinstance(alert, Mapping)))}


def _build_next_steps(phase: str, alerts: Sequence[Mapping[str, Any]], positive_target_count: int, submitted_count: int, open_order_count: int) -> list[str]:
    alert_codes = {str(alert.get("code", "")).strip().lower() for alert in alerts}
    steps: list[str] = []
    if phase == "research":
        steps.append("开盘前运行执行任务，让券商按这份目标仓位提单。" if positive_target_count > 0 else "这轮没有新目标仓位，开盘前先确认是不是数据或风控条件把候选股都过滤掉了。")
    else:
        if submitted_count > 0:
            steps.append("先看 Alpaca 模拟账户里的未完成订单，确认数量和简报里的已提订单数一致。")
        if open_order_count > 0:
            steps.append("挂单未成交时，账户持仓可能暂时还是空的，这属于正常中间态。")
    if "open_orders_lingering" in alert_codes:
        steps.append("如果多轮后挂单仍在，优先检查是否需要等待成交或手动撤单后再重跑。")
    if "data_stale" in alert_codes:
        steps.append("下一轮先补研究产物，避免继续沿用过期交易日的信号。")
    return (steps or ["当前没有明显阻塞项，按计划等待下一次定时运行即可。"])[:4]


def _build_beginner_notes(phase: str, account: Mapping[str, Any], open_order_count: int, positive_target_count: int, submitted_count: int) -> list[str]:
    notes: list[str] = []
    cash = _coerce_float(account.get("cash"))
    buying_power = _coerce_float(account.get("buying_power"))
    if cash is not None and buying_power is not None and buying_power > cash + 1e-9:
        notes.append("可用购买力高于现金在 Alpaca 模拟账户里很常见，通常是保证金额度，不代表账户里多了真实现金。")
    if phase == "research" and positive_target_count > 0:
        notes.append("研究简报里看到的是计划仓位，不是已经成交的持仓；真正下单要等开盘后的开盘执行任务。")
    if phase == "submit" and submitted_count > 0:
        notes.append("已提订单代表指令已经发给券商；只有状态变成已成交，仓位才算真正买入或卖出。")
    if phase == "submit" and open_order_count > 0:
        notes.append("当未完成订单还存在时，账户里的持仓可能还是空的，这属于成交前的正常中间态。")
    return notes[:4]


def _human_summary(phase: str, strategy_label: str, top_positions: Sequence[Mapping[str, Any]], exit_symbols: Sequence[str], submitted_count: int, open_order_count: int) -> str:
    leaders = ", ".join(f"{item.get('symbol', '')} {((_coerce_float(item.get('target_weight')) or 0.0) * 100):.1f}%" for item in top_positions if item.get("symbol"))
    exits = ", ".join(item for item in exit_symbols if item)
    if phase == "research":
        if leaders and exits:
            return f"{strategy_label} 下一轮更偏向持有 {leaders}，同时退出 {exits}。"
        return f"{strategy_label} 下一轮重点仓位会集中在 {leaders or '暂无'}。"
    if submitted_count > 0:
        return f"{strategy_label} 已经向模拟券商发出 {submitted_count} 笔订单，其中仍在等待成交的有 {open_order_count} 笔。"
    return f"{strategy_label} 本轮没有新的提单结果。"


def _chart_summary(strategy: Mapping[str, Any]) -> str:
    leaders = ", ".join(f"{item.get('symbol', '')} {((_coerce_float(item.get('target_weight')) or 0.0) * 100):.0f}%" for item in list(strategy.get("top_positions") or [])[:3] if item.get("symbol"))
    return f"已提订单 {int(strategy.get('submitted_count', 0))} 笔；仍未完成 {int(strategy.get('open_order_count', 0))} 笔。" if strategy.get("phase") == "submit" else f"重点计划持仓：{leaders or '暂无'}。"


def _localize_alert(alert: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(alert)
    code = _normalize(payload.get("code"))
    localized = ALERT_COPY.get(code)
    if not localized:
        return payload
    payload["title"] = localized["title"]
    payload["message"] = localized["message"]
    return payload


def _classify_submit_order_fulfillment(*, order_statuses: Sequence[Mapping[str, Any]], submitted_count: int) -> dict[str, Any]:
    normalized_statuses = [
        _normalize(item.get("status"))
        for item in order_statuses
        if isinstance(item, Mapping)
    ]
    status_count = len(normalized_statuses)
    terminal_order_count = sum(status in TERMINAL_ORDER_STATUSES for status in normalized_statuses)
    rejected_count = sum(status in {"rejected", "reject"} or "reject" in status for status in normalized_statuses)
    non_terminal_count = max(0, status_count - terminal_order_count)
    missing_status_count = max(0, submitted_count - terminal_order_count)
    open_order_count = max(non_terminal_count, missing_status_count)
    has_rejected = rejected_count > 0
    is_final = submitted_count <= 0 or open_order_count == 0
    execution_state = "final" if is_final else "provisional"
    coverage = "n/a" if submitted_count <= 0 else f"{terminal_order_count}/{submitted_count}"
    return {
        "submitted_count": int(submitted_count),
        "status_count": status_count,
        "terminal_order_count": terminal_order_count,
        "open_order_count": open_order_count,
        "rejected_count": rejected_count,
        "has_rejected": has_rejected,
        "coverage": coverage,
        "is_final": is_final,
        "execution_state": execution_state,
    }


def _derive_submit_execution_state(*, strategies: Sequence[Mapping[str, Any]]) -> str:
    if not strategies:
        return "final"
    return "final" if all(str(item.get("execution_state") or "") == "final" for item in strategies) else "provisional"


def _derive_submit_brief_status(*, strategies: Sequence[Mapping[str, Any]], requested_status: str) -> str:
    requested_status = str(requested_status or "success")
    if requested_status == "failed":
        return "failed"
    if not strategies:
        return requested_status if requested_status in STATUS_STYLES else "success"

    total_open = sum(int(item.get("open_order_count", 0)) for item in strategies)
    any_provisional = any(str(item.get("execution_state") or "") == "provisional" for item in strategies)
    any_refresh_failed = any(
        bool(strategy.get("distribution_refresh", {}).get("attempted")) and not bool(strategy.get("distribution_refresh", {}).get("ok"))
        for strategy in strategies
    )
    any_rejected = any(
        bool(item.get("has_rejected_orders")) or int(item.get("order_settlement", {}).get("rejected_count", 0)) > 0
        for item in strategies
    )
    all_final = all(str(item.get("execution_state") or "") == "final" for item in strategies)
    submitted_strategies = [item for item in strategies if int(item.get("submitted_count", 0)) > 0]
    failed_terminal_strategies = [
        item
        for item in submitted_strategies
        if int(item.get("open_order_count", 0)) == 0
        and int(item.get("order_settlement", {}).get("terminal_order_count", 0)) > 0
        and int(item.get("order_settlement", {}).get("terminal_order_count", 0)) == int(item.get("order_settlement", {}).get("rejected_count", 0))
    ]

    if submitted_strategies and len(failed_terminal_strategies) == len(submitted_strategies):
        return "failed"
    if any_provisional:
        return "partial"
    if any_rejected or total_open > 0 or any_refresh_failed:
        return "partial"
    if all_final:
        return "success"
    return "partial" if requested_status == "partial" else "success"


def _try_refresh_live_alpaca_snapshot(*, paper_env_prefix: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": False,
        "ok": False,
        "reason": "not_attempted",
        "account_snapshot": {},
        "positions_snapshot": [],
    }
    prefix = str(paper_env_prefix or "").strip()
    if not prefix:
        result["reason"] = "missing_paper_env_prefix"
        return result

    result["attempted"] = True
    try:
        credentials = load_alpaca_credentials(prefix)
        broker = AlpacaBroker(credentials)
        account_snapshot = broker.get_account_snapshot().to_dict()
        positions_snapshot = [item.to_dict() for item in broker.list_positions()]
        equity = _coerce_float(account_snapshot.get("equity")) or 0.0
        if equity <= 0:
            equity = sum(abs(_coerce_float(item.get("market_value")) or 0.0) for item in positions_snapshot)
        for item in positions_snapshot:
            market_value = abs(_coerce_float(item.get("market_value")) or 0.0)
            item["weight"] = (market_value / equity) if equity > 0 else 0.0
        positions_snapshot.sort(key=lambda item: abs(_coerce_float(item.get("market_value")) or 0.0), reverse=True)
        result.update(
            {
                "ok": True,
                "reason": "ok",
                "account_snapshot": account_snapshot,
                "positions_snapshot": positions_snapshot,
            }
        )
    except Exception as exc:
        result["reason"] = f"refresh_failed:{type(exc).__name__}"
        result["error"] = str(exc)
    return result


def _latest_rebalance_date(rows: Sequence[Mapping[str, Any]]) -> str:
    dates = [str(row.get("rebalance_date", "")).strip() for row in rows if row.get("rebalance_date")]
    return max(dates) if dates else ""


def _parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value in (None, ""):
        return {}
    try:
        parsed = ast.literal_eval(str(value))
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _load_json_mapping(path_value: Any) -> dict[str, Any]:
    path = _resolve_path(path_value)
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _load_json_list(path_value: Any) -> list[dict[str, Any]]:
    path = _resolve_path(path_value)
    if path is None or not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [dict(item) for item in payload if isinstance(item, Mapping)] if isinstance(payload, list) else []


def _extract_analysis_pool_symbols(
    *,
    config: Mapping[str, Any],
    config_path: Path,
    source_frame: pd.DataFrame,
    rebalance_date: str,
    fallback_symbols: Sequence[str],
    max_symbols: int,
) -> tuple[list[str], str]:
    max_symbols = int(max(1, max_symbols))
    analysis_cfg = dict(config.get("analysis") or {})
    research_cfg = dict(config.get("research") or {})
    source_cfg = dict(config.get("source") or {})

    symbols = _first_non_empty_symbol_list(
        [
            config.get("watchlist_symbols"),
            config.get("symbol_pool"),
            config.get("pool_symbols"),
            research_cfg.get("watchlist_symbols"),
            research_cfg.get("symbol_pool"),
            analysis_cfg.get("watchlist_symbols"),
            analysis_cfg.get("symbol_pool"),
            source_cfg.get("watchlist_symbols"),
            source_cfg.get("symbol_pool"),
        ],
        limit=max_symbols,
    )
    if symbols:
        return symbols, "config_symbols"

    file_candidates = [
        config.get("watchlist_file"),
        config.get("symbols_file"),
        config.get("symbol_pool_file"),
        research_cfg.get("watchlist_file"),
        research_cfg.get("symbols_file"),
        analysis_cfg.get("watchlist_file"),
        analysis_cfg.get("symbols_file"),
        source_cfg.get("symbols_file"),
    ]
    for path_value in file_candidates:
        path = _resolve_symbols_path(path_value=path_value, config_path=config_path)
        if path is None or not path.exists():
            continue
        rows = _load_symbols_from_file(path)
        if rows:
            return rows[:max_symbols], "config_file"

    inferred = _infer_pool_symbols_from_source_frame(
        source_frame=source_frame,
        rebalance_date=rebalance_date,
        limit=max_symbols,
    )
    if inferred:
        return inferred, "source_frame"

    fallback = _normalize_symbols(fallback_symbols, limit=max_symbols)
    if fallback:
        return fallback, "targets_fallback"
    return [], "empty"


def _resolve_research_curve_source_frame(
    *,
    config: Mapping[str, Any],
    config_path: Path,
    fallback_source_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, str]:
    analysis_cfg = dict(config.get("analysis") or {})
    research_cfg = dict(config.get("research") or {})
    source_cfg = dict(config.get("source") or {})
    explicit_candidates = [
        research_cfg.get("market_curves_source_path"),
        research_cfg.get("curves_source_path"),
        research_cfg.get("universe_csv"),
        analysis_cfg.get("market_curves_source_path"),
        analysis_cfg.get("curves_source_path"),
        source_cfg.get("market_curves_source_path"),
        source_cfg.get("curves_source_path"),
    ]
    for candidate in explicit_candidates:
        path = _resolve_symbols_path(path_value=candidate, config_path=config_path)
        if path is None or not path.exists():
            continue
        frame = _load_source_frame(path)
        if not frame.empty:
            return frame, f"config:{path}"

    auto_path = _find_latest_market_universe_csv()
    if auto_path is not None and auto_path.exists():
        auto_frame = _load_source_frame(auto_path)
        if not auto_frame.empty:
            return auto_frame, f"auto:{auto_path}"

    if not fallback_source_frame.empty:
        return fallback_source_frame, "strategy_source"
    return fallback_source_frame, "empty"


def _resolve_research_curve_lookback(
    *,
    config: Mapping[str, Any],
    expert_snapshot: Mapping[str, Any],
) -> tuple[int, int, str]:
    research_cfg = dict(config.get("research") or {})
    analysis_cfg = dict(config.get("analysis") or {})

    explicit_lookback = (
        _coerce_float(research_cfg.get("curve_lookback"))
        or _coerce_float(analysis_cfg.get("curve_lookback"))
        or _coerce_float(research_cfg.get("research_curve_lookback"))
        or _coerce_float(analysis_cfg.get("research_curve_lookback"))
    )
    if explicit_lookback and explicit_lookback > 0:
        lookback = int(max(8, min(240, round(explicit_lookback))))
        return lookback, max(1, lookback // 2), "config"

    multiplier = int(
        max(
            1,
            min(
                4,
                round(
                    _coerce_float(research_cfg.get("curve_lookback_multiplier"))
                    or _coerce_float(analysis_cfg.get("curve_lookback_multiplier"))
                    or 2.0
                ),
            ),
        )
    )
    expert_input_window = _infer_expert_input_window(expert_snapshot=expert_snapshot)
    if expert_input_window <= 0:
        fallback_window = (
            _coerce_float(research_cfg.get("fallback_input_window"))
            or _coerce_float(analysis_cfg.get("fallback_input_window"))
            or 35.0
        )
        expert_input_window = int(max(5, min(120, round(fallback_window))))
    lookback = int(max(8, min(240, expert_input_window * multiplier)))
    return lookback, expert_input_window, f"expert_input_x{multiplier}"


def _infer_expert_input_window(*, expert_snapshot: Mapping[str, Any]) -> int:
    manifest_path = _resolve_path(expert_snapshot.get("manifest_path"))
    if manifest_path is None or not manifest_path.exists():
        return 0
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return 0

    summary = manifest.get("summary") if isinstance(manifest.get("summary"), Mapping) else {}
    horizon_fallback = int(max(0, _coerce_float(summary.get("horizon")) or 0.0))
    source_metadata = manifest.get("source_metadata")
    if not isinstance(source_metadata, list):
        source_metadata = summary.get("source_metadata") if isinstance(summary, Mapping) else []

    windows: list[int] = []
    if isinstance(source_metadata, list):
        for item in source_metadata:
            if not isinstance(item, Mapping):
                continue
            model_name = str(item.get("model_name", "")).lower().strip()
            prediction_csv = _resolve_path(item.get("prediction_csv"))
            if prediction_csv is None:
                continue

            model_windows: list[int] = []
            for metadata_filename in ("predict_summary.json", "metrics.json", "model_metadata.json"):
                metadata_path = prediction_csv.parent / metadata_filename
                if not metadata_path.exists():
                    continue
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(metadata, Mapping):
                    continue
                model_windows.extend(
                    _extract_input_window_from_metadata(metadata=metadata)
                )

            if not model_windows:
                default_window = int(DEFAULT_EXPERT_INPUT_WINDOWS.get(model_name, 0))
                if default_window > 0:
                    model_windows.append(default_window)

            windows.extend(value for value in model_windows if value > 0)

    if not windows and horizon_fallback > 0:
        return horizon_fallback
    return int(max(windows)) if windows else 0


def _extract_input_window_from_metadata(*, metadata: Mapping[str, Any]) -> list[int]:
    keys = (
        "lookback",
        "seq_len",
        "sequence_len",
        "sequence_window",
        "sequence_length",
        "input_window",
        "window",
    )
    candidates: list[int] = []
    for key in keys:
        value = _coerce_float(metadata.get(key))
        if value is None:
            continue
        numeric = int(round(value))
        if 1 <= numeric <= 252:
            candidates.append(numeric)

    feature_columns = metadata.get("feature_columns")
    if isinstance(feature_columns, Sequence) and not isinstance(feature_columns, (str, bytes)):
        candidates.extend(_extract_max_window_from_feature_columns(feature_columns=feature_columns))

    horizon = _coerce_float(metadata.get("horizon"))
    if horizon is not None:
        horizon_numeric = int(round(horizon))
        if 1 <= horizon_numeric <= 252:
            candidates.append(horizon_numeric)
    return candidates


def _extract_max_window_from_feature_columns(*, feature_columns: Sequence[Any]) -> list[int]:
    max_window = 0
    pattern = re.compile(r"(?:^|[_-])(\d{1,3})(?:d|$|[_-])")
    for raw_name in feature_columns:
        name = str(raw_name or "").lower().strip()
        if not name:
            continue
        for match in pattern.finditer(name):
            try:
                value = int(match.group(1))
            except Exception:
                continue
            if 1 <= value <= 252:
                max_window = max(max_window, value)
    return [max_window] if max_window > 0 else []


def _find_latest_market_universe_csv() -> Path | None:
    interim_root = PROJECT_ROOT / "data" / "interim"
    if not interim_root.exists():
        return None

    candidates: list[Path] = []
    preferred_patterns = [
        interim_root / "alpaca" / "universes",
        interim_root / "stooq" / "universes",
    ]
    for folder in preferred_patterns:
        if not folder.exists():
            continue
        candidates.extend(sorted(folder.glob("us_large_cap_30_*_normalized.csv")))
        candidates.extend(sorted(folder.glob("*_normalized.csv")))

    for path in interim_root.glob("*/*/*_normalized.csv"):
        if path.is_file():
            candidates.append(path)

    if not candidates:
        return None

    unique: dict[str, Path] = {str(path.resolve()): path for path in candidates if path.exists()}
    if not unique:
        return None
    return max(unique.values(), key=lambda item: item.stat().st_mtime)


def _build_pool_expected_weights(
    *,
    pool_symbols: Sequence[str],
    target_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_symbol: dict[str, float] = {}
    for row in target_rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        weight = max(0.0, _coerce_float(row.get("target_weight")) or 0.0)
        by_symbol[symbol] = weight
    return [
        {"symbol": symbol, "target_weight": float(by_symbol.get(symbol, 0.0))}
        for symbol in _normalize_symbols(pool_symbols, limit=len(pool_symbols) or 0)
    ]


def _pick_expert_symbols_for_snapshot(
    *,
    pool_expected_weights: Sequence[Mapping[str, Any]],
    fallback_symbols: Sequence[str],
    limit: int,
) -> list[str]:
    weighted = [
        (str(item.get("symbol", "")).upper().strip(), _coerce_float(item.get("target_weight")) or 0.0)
        for item in pool_expected_weights
        if isinstance(item, Mapping)
    ]
    weighted = [(symbol, weight) for symbol, weight in weighted if symbol]
    weighted.sort(key=lambda item: item[1], reverse=True)
    selected: list[str] = []
    seen: set[str] = set()
    for symbol, weight in weighted:
        if weight <= 1e-9 or symbol in seen:
            continue
        selected.append(symbol)
        seen.add(symbol)
        if len(selected) >= limit:
            return selected
    for symbol, _ in weighted:
        if symbol in seen:
            continue
        selected.append(symbol)
        seen.add(symbol)
        if len(selected) >= limit:
            return selected
    if selected:
        return selected
    fallback = _normalize_symbols(fallback_symbols, limit=limit)
    if fallback:
        return fallback
    return [symbol for symbol, _ in weighted[:limit]]


def _first_non_empty_symbol_list(candidates: Sequence[Any], *, limit: int) -> list[str]:
    for candidate in candidates:
        symbols = _normalize_symbols(candidate, limit=limit)
        if symbols:
            return symbols
    return []


def _normalize_symbols(value: Any, *, limit: int) -> list[str]:
    if limit <= 0:
        return []
    rows: list[str] = []
    if isinstance(value, str):
        chunks = [part.strip() for part in value.replace("\n", ",").split(",")]
        rows.extend(chunks)
    elif isinstance(value, Sequence):
        rows.extend(str(item).strip() for item in value if str(item).strip())
    else:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in rows:
        symbol = str(raw).upper().strip()
        if not symbol or symbol in seen:
            continue
        if not all(char.isalnum() or char in {".", "-", "_"} for char in symbol):
            continue
        normalized.append(symbol)
        seen.add(symbol)
        if len(normalized) >= limit:
            break
    return normalized


def _resolve_symbols_path(*, path_value: Any, config_path: Path) -> Path | None:
    if path_value in (None, ""):
        return None
    raw_path = Path(str(path_value))
    if raw_path.is_absolute():
        return raw_path
    candidate = (config_path.parent / raw_path).resolve()
    if candidate.exists():
        return candidate
    return _resolve_path(raw_path)


def _load_symbols_from_file(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    return _normalize_symbols(
        [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")],
        limit=500,
    )


def _infer_pool_symbols_from_source_frame(*, source_frame: pd.DataFrame, rebalance_date: str, limit: int) -> list[str]:
    if source_frame.empty or "symbol" not in source_frame.columns:
        return []
    frame = source_frame.copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper().str.strip()
    frame = frame[frame["symbol"] != ""]
    if frame.empty:
        return []
    if "date" in frame.columns:
        frame["date"] = frame["date"].astype(str)
        if rebalance_date:
            bounded = frame[frame["date"] <= str(rebalance_date)]
            if not bounded.empty:
                latest_date = str(bounded["date"].max())
                frame = bounded[bounded["date"] == latest_date]
    if "score" in frame.columns:
        frame["score_abs"] = pd.to_numeric(frame["score"], errors="coerce").abs().fillna(0.0)
        frame = frame.sort_values(["score_abs", "symbol"], ascending=[False, True], kind="stable")
    else:
        frame = frame.sort_values(["symbol"], kind="stable")
    symbols = frame["symbol"].dropna().astype(str).tolist()
    return _normalize_symbols(symbols, limit=limit)


def _resolve_path(path_value: Any) -> Path | None:
    if path_value in (None, ""):
        return None
    path = Path(str(path_value))
    return path if path.is_absolute() else PROJECT_ROOT / path


def _sync_latest(source_dir: Path, latest_dir: Path) -> None:
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(source_dir, latest_dir)


def _summarize_source_metrics(summary: Mapping[str, Any]) -> dict[str, Any]:
    if not summary:
        return {}
    return {"model_name": summary.get("model_name"), "annualized_return": _coerce_float(summary.get("annualized_return")), "excess_total_return": _coerce_float(summary.get("excess_total_return")), "win_rate": _coerce_float(summary.get("win_rate")), "max_drawdown": _coerce_float(summary.get("max_drawdown")), "periods": int(summary.get("periods") or 0)}


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(numeric) else numeric


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower() or "unknown"


def _build_feishu_signature(*, timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    signature = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(signature).decode("utf-8")
