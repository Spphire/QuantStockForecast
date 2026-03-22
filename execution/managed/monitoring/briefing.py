from __future__ import annotations

import ast
import json
import math
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
import requests

from execution.common.strategy_runtime import load_strategy_config, load_target_positions
from execution.managed.monitoring.alerts import build_operator_alerts
from execution.managed.monitoring.healthcheck import build_paper_daily_healthcheck


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BRIEF_ROOT = PROJECT_ROOT / "artifacts" / "ops_briefs"
DEFAULT_NOTIFICATION_CONFIG = PROJECT_ROOT / "configs" / "ops_notifications.local.json"

PHASE_TITLES = {"research": "Nightly Research Brief", "submit": "Market Open Submit Brief"}
STATUS_STYLES = {
    "success": {"label": "On Track", "color": "#0b6e4f", "background": "#dff3ea"},
    "partial": {"label": "Needs Attention", "color": "#9c6500", "background": "#fff2d8"},
    "failed": {"label": "Run Failed", "color": "#9b1c1c", "background": "#fde4e1"},
}
PIE_COLORS = ["#0b6e4f", "#1b998b", "#ffb703", "#e76f51", "#8ecae6", "#adb5bd"]
BAR_COLORS = ["#1d3557", "#457b9d", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"]
ACTION_LABELS = {"open": "Open", "add": "Add", "reduce": "Reduce", "hold": "Hold", "exit": "Exit", "accepted": "Accepted", "filled": "Filled", "rejected": "Rejected", "canceled": "Canceled", "cancelled": "Canceled", "expired": "Expired"}


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

    brief = {
        "phase": phase,
        "title": title or PHASE_TITLES[phase],
        "status": status,
        "status_display": STATUS_STYLES[status]["label"],
        "notes": [str(note).strip() for note in (notes or ()) if str(note).strip()],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference_date": (reference_date or date.today()).isoformat(),
        "strategies": [
            build_strategy_brief(strategy_config=Path(path), phase=phase, reference_date=reference_date)
            for path in strategy_configs
        ],
    }
    brief["strategy_count"] = len(brief["strategies"])
    brief["summary"] = _build_summary(brief["strategies"], phase=phase, status=status)

    root = Path(output_root) if output_root else DEFAULT_BRIEF_ROOT / phase
    run_dir = root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    dashboard_path = run_dir / "dashboard.png"
    markdown_path = run_dir / "brief.md"
    html_path = run_dir / "brief.html"
    json_path = run_dir / "brief.json"

    _render_dashboard(brief=brief, output_path=dashboard_path)
    markdown_path.write_text(_build_markdown(brief, dashboard_path.name), encoding="utf-8")
    html_path.write_text(_build_html(brief, dashboard_path.name), encoding="utf-8")
    json_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_dir = root / "latest"
    _sync_latest(run_dir, latest_dir)
    notification = _maybe_send_notifications(brief=brief, run_dir=run_dir, html_path=html_path) if notify else {"enabled": False, "reason": "notify_disabled"}

    return {
        "ok": True,
        "phase": phase,
        "title": brief["title"],
        "status": brief["status"],
        "status_display": brief["status_display"],
        "notes": brief["notes"],
        "generated_at_utc": brief["generated_at_utc"],
        "run_dir": str(run_dir),
        "latest_dir": str(latest_dir),
        "dashboard_png": str(dashboard_path),
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "json_path": str(json_path),
        "notification": notification,
        "summary": brief["summary"],
        "strategies": brief["strategies"],
    }


def build_strategy_brief(*, strategy_config: str | Path, phase: str, reference_date: date | None = None) -> dict[str, Any]:
    config_path = Path(strategy_config)
    config = load_strategy_config(config_path)
    strategy_id = str(config["strategy_id"])
    source = dict(config.get("source") or {})
    execution = dict(config.get("execution") or {})
    healthcheck = build_paper_daily_healthcheck(strategy_id, reference_date=reference_date)
    latest_state = dict(healthcheck.latest_state or {})
    if phase != "submit":
        latest_state = {}
    source_path = latest_state.get("targets_csv_path") if phase == "submit" else source.get("path")
    actions_path = None if phase == "submit" else source.get("actions_path")
    targets = _load_targets(source_path=source_path or source.get("path"), actions_path=actions_path, rebalance_selection=str(execution.get("rebalance_selection") or "latest"))
    target_rows = [target.to_dict() for target in targets]
    positive_targets = [row for row in target_rows if (_coerce_float(row.get("target_weight")) or 0.0) > 0]
    positive_targets.sort(key=lambda item: _coerce_float(item.get("target_weight")) or 0.0, reverse=True)
    exit_rows = [row for row in target_rows if str(row.get("action", "")).lower() == "exit" or (_coerce_float(row.get("target_weight")) or 0.0) <= 0.0]
    order_statuses = _load_json_list(latest_state.get("submitted_order_statuses_path")) if phase == "submit" else []
    alerts = [alert.to_dict() for alert in build_operator_alerts(state_payload=latest_state, reference_date=reference_date)] if phase == "submit" else []
    source_summary = _load_json_mapping((latest_state.get("source_summary_path") or source.get("summary_path"))) if (phase == "submit" or source.get("summary_path")) else {}
    account_snapshot = _load_json_mapping(latest_state.get("account_path")) if phase == "submit" else {}
    buffer = _coerce_float(latest_state.get("buying_power_buffer")) or _coerce_float(execution.get("buying_power_buffer")) or 1.0
    account_equity = _coerce_float(latest_state.get("account_equity")) or _coerce_float(account_snapshot.get("equity")) or _coerce_float(execution.get("default_account_equity")) or 0.0
    planning_equity = _coerce_float(latest_state.get("planning_equity")) or (account_equity * buffer)
    top_positions = [_decorate_target(row, planning_equity) for row in positive_targets[:5]]
    open_order_count = len([item for item in order_statuses if _normalize(item.get("status")) not in {"filled", "canceled", "cancelled", "rejected", "expired"}])

    return {
        "strategy_id": strategy_id,
        "strategy_name": str(config.get("description") or strategy_id),
        "config_path": str(config_path.resolve()),
        "phase": phase,
        "rebalance_date": _latest_rebalance_date(target_rows) or latest_state.get("rebalance_date"),
        "description": str(config.get("description") or ""),
        "top_positions": top_positions,
        "exit_symbols": [str(row.get("symbol", "")).upper() for row in exit_rows[:5]],
        "positive_target_count": len(positive_targets),
        "exit_count": len(exit_rows),
        "action_counts": dict(Counter(_normalize(row.get("action")) for row in target_rows)),
        "order_status_counts": dict(Counter(_normalize(item.get("status")) for item in order_statuses)),
        "submitted_count": int(latest_state.get("submitted_count") or len(order_statuses)),
        "open_order_count": open_order_count,
        "account": {"equity": account_equity, "cash": _coerce_float(account_snapshot.get("cash")), "buying_power": _coerce_float(latest_state.get("account_buying_power")) or _coerce_float(account_snapshot.get("buying_power")), "planning_equity": planning_equity, "buying_power_buffer": buffer, "currency": account_snapshot.get("currency") or "USD"},
        "alerts": alerts,
        "healthcheck_reasons": list(healthcheck.reasons) if phase == "submit" else [],
        "source_summary": _summarize_source_metrics(source_summary),
        "paths": {"source_path": str(_resolve_path(source_path or source.get("path"))) if (source_path or source.get("path")) else "", "summary_path": str(_resolve_path(source.get("summary_path") or latest_state.get("source_summary_path"))) if (source.get("summary_path") or latest_state.get("source_summary_path")) else "", "run_dir": str(_resolve_path(latest_state.get("run_dir"))) if latest_state.get("run_dir") else "", "latest_state_path": healthcheck.state_path},
        "latest_state": latest_state if phase == "submit" else {},
        "explain_like_human": _human_summary(phase, strategy_id, top_positions[:3], [str(row.get("symbol", "")).upper() for row in exit_rows[:3]], int(latest_state.get("submitted_count") or len(order_statuses)), open_order_count),
        "next_steps": _build_next_steps(phase, alerts, len(positive_targets), int(latest_state.get("submitted_count") or len(order_statuses)), open_order_count),
        "beginner_notes": _build_beginner_notes(phase, {"cash": _coerce_float(account_snapshot.get("cash")), "buying_power": _coerce_float(latest_state.get("account_buying_power")) or _coerce_float(account_snapshot.get("buying_power"))}, open_order_count, len(positive_targets), int(latest_state.get("submitted_count") or len(order_statuses))),
    }


def _load_targets(*, source_path: str | Path | None, actions_path: str | Path | None, rebalance_selection: str) -> list[Any]:
    resolved_source = _resolve_path(source_path)
    if resolved_source is None or not resolved_source.exists():
        return []
    return load_target_positions(resolved_source, rebalance_selection, actions_path=_resolve_path(actions_path))


def _render_dashboard(brief: Mapping[str, Any], output_path: Path) -> None:
    strategies = list(brief.get("strategies", []))
    rows = max(1, len(strategies))
    fig, axes = plt.subplots(rows, 2, figsize=(15, max(6.2, 4.6 * rows)))
    fig.patch.set_facecolor("#f7f3eb")
    if rows == 1:
        axes = [axes]
    for idx, strategy in enumerate(strategies):
        _draw_allocation(axes[idx][0], strategy)
        _draw_activity(axes[idx][1], strategy)
    summary = dict(brief.get("summary") or {})
    fig.suptitle(str(brief.get("title") or "Operations Brief"), fontsize=18, fontweight="bold", y=0.98, color="#102a43")
    fig.text(0.5, 0.945, " | ".join([STATUS_STYLES.get(str(brief.get("status")), STATUS_STYLES["success"])["label"], f"Generated {brief.get('generated_at_utc', '')} UTC", f"Strategies {summary.get('strategy_count', 0)}", f"Targets {summary.get('positive_target_count', 0)}", f"Submitted {summary.get('submitted_count', 0)}", f"Open Orders {summary.get('open_order_count', 0)}"]), ha="center", va="center", fontsize=10, color="#52606d")
    plt.tight_layout(rect=(0.02, 0.02, 0.98, 0.92))
    fig.savefig(output_path, dpi=180, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def _draw_allocation(ax: Any, strategy: Mapping[str, Any]) -> None:
    top_positions = list(strategy.get("top_positions") or [])
    if not top_positions:
        ax.axis("off")
        ax.text(0.5, 0.5, "No active targets", ha="center", va="center", fontsize=12, color="#52606d")
        return
    labels = [str(item.get("symbol", "")) for item in top_positions]
    weights = [_coerce_float(item.get("target_weight")) or 0.0 for item in top_positions]
    remainder = max(0.0, 1.0 - sum(weights))
    if remainder > 0.001:
        labels.append("Cash/Other")
        weights.append(remainder)
    ax.pie(weights, labels=labels, colors=PIE_COLORS[: len(weights)], startangle=120, autopct=lambda pct: f"{pct:.1f}%" if pct > 4 else "", wedgeprops={"width": 0.45, "edgecolor": "#ffffff"}, textprops={"fontsize": 9, "color": "#102a43"})
    ax.set_title(f"{strategy.get('strategy_id', '')}\nTarget Allocation", fontsize=12, fontweight="bold", color="#102a43", pad=12)
    ax.text(0.0, -1.22, _chart_summary(strategy), ha="center", va="center", fontsize=9, color="#334e68", wrap=True, transform=ax.transData)


def _draw_activity(ax: Any, strategy: Mapping[str, Any]) -> None:
    counts = dict(strategy.get("order_status_counts") or {}) if strategy.get("phase") == "submit" and strategy.get("order_status_counts") else dict(strategy.get("action_counts") or {})
    title = "Broker Order Status" if strategy.get("phase") == "submit" and strategy.get("order_status_counts") else "Action Mix"
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
        ax.text(0.5, 0.5, "No activity data", ha="center", va="center", fontsize=12, color="#52606d")
    ax.set_title(f"{strategy.get('strategy_id', '')}\n{title}", fontsize=12, fontweight="bold", color="#102a43", pad=12)
    ax.grid(axis="y", color="#d9e2ec", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(0.02, 0.98, _metrics_text(strategy), transform=ax.transAxes, ha="left", va="top", fontsize=9, color="#102a43", bbox={"boxstyle": "round,pad=0.45", "facecolor": "#fffdf8", "edgecolor": "#d9e2ec"})


def _build_markdown(brief: Mapping[str, Any], dashboard_name: str) -> str:
    lines = [f"# {brief.get('title', 'Operations Brief')}", "", f"- Phase: `{brief.get('phase', '')}`", f"- Status: `{brief.get('status_display', '')}`", f"- Generated At (UTC): `{brief.get('generated_at_utc', '')}`", "", f"![dashboard]({dashboard_name})", ""]
    for strategy in brief.get("strategies", []):
        lines.extend([f"## {strategy.get('strategy_id', '')}", "", str(strategy.get("explain_like_human") or ""), "", f"- Rebalance Date: `{strategy.get('rebalance_date') or 'n/a'}`", f"- Targets: `{strategy.get('positive_target_count', 0)}`", f"- Exit Symbols: `{', '.join(strategy.get('exit_symbols', [])) or 'n/a'}`", f"- Submitted Orders: `{strategy.get('submitted_count', 0)}`", f"- Open Orders: `{strategy.get('open_order_count', 0)}`", "", "| Symbol | Weight | Planned Notional | Industry |", "| --- | ---: | ---: | --- |"])
        for item in strategy.get("top_positions", []):
            lines.append("| {symbol} | {weight:.1f}% | {notional} | {industry} |".format(symbol=item.get("symbol", ""), weight=(_coerce_float(item.get("target_weight")) or 0.0) * 100, notional=(f"{(_coerce_float(item.get('planned_notional')) or 0.0):,.0f}" if _coerce_float(item.get("planned_notional")) is not None else "n/a"), industry=item.get("industry_group", "") or "-"))
        lines.extend(["", "Next Steps:"])
        lines.extend(f"- {step}" for step in strategy.get("next_steps", []))
        lines.extend(["", "Beginner Notes:"])
        lines.extend(f"- {note}" for note in strategy.get("beginner_notes", []))
        if strategy.get("alerts"):
            lines.extend(["", "Alerts:"])
            lines.extend(f"- [{alert.get('severity', 'info')}] {alert.get('title', '')}: {alert.get('message', '')}" for alert in strategy.get("alerts", []))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_html(brief: Mapping[str, Any], dashboard_name: str) -> str:
    summary = dict(brief.get("summary") or {})
    status_style = STATUS_STYLES.get(str(brief.get("status")), STATUS_STYLES["success"])
    cards = "".join(f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>' for label, value in (("Strategies", summary.get("strategy_count", 0)), ("Targets", summary.get("positive_target_count", 0)), ("Submitted", summary.get("submitted_count", 0)), ("Open Orders", summary.get("open_order_count", 0))))
    sections = []
    for strategy in brief.get("strategies", []):
        rows = "".join("<tr><td>{symbol}</td><td>{weight:.1f}%</td><td>{industry}</td><td>{notional}</td></tr>".format(symbol=item.get("symbol", ""), weight=(_coerce_float(item.get("target_weight")) or 0.0) * 100, industry=item.get("industry_group", "") or "-", notional=(f"{(_coerce_float(item.get('planned_notional')) or 0.0):,.0f}" if _coerce_float(item.get("planned_notional")) is not None else "n/a")) for item in strategy.get("top_positions", []))
        badges = "".join(f'<span class="badge {str(alert.get("severity", "info"))}">{alert.get("title", alert.get("code", ""))}</span>' for alert in strategy.get("alerts", [])) or '<span class="badge info">No active alerts</span>'
        next_steps = "".join(f"<li>{step}</li>" for step in strategy.get("next_steps", []))
        beginner_notes = "".join(f"<li>{note}</li>" for note in strategy.get("beginner_notes", []))
        sections.append(f'<section class="section"><h2>{strategy.get("strategy_id", "")}</h2><p class="summary">{strategy.get("explain_like_human", "")}</p><div class="meta"><span>Rebalance: {strategy.get("rebalance_date") or "n/a"}</span><span>Targets: {strategy.get("positive_target_count", 0)}</span><span>Exit: {strategy.get("exit_count", 0)}</span><span>Submitted: {strategy.get("submitted_count", 0)}</span><span>Open Orders: {strategy.get("open_order_count", 0)}</span></div><div class="badges">{badges}</div><table><thead><tr><th>Symbol</th><th>Weight</th><th>Industry</th><th>Planned Notional</th></tr></thead><tbody>{rows}</tbody></table><div class="notes-grid"><div><h3>Next Steps</h3><ul>{next_steps}</ul></div><div><h3>Beginner Notes</h3><ul>{beginner_notes}</ul></div></div></section>')
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{brief.get("title", "Operations Brief")}</title><style>body{{margin:0;padding:32px;background:linear-gradient(180deg,#f7f3eb,#fffdf9);color:#102a43;font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}}.hero,.section{{max-width:1120px;margin:0 auto 20px auto;background:rgba(255,255,255,0.9);border:1px solid #eadfce;border-radius:20px;padding:24px 28px;box-shadow:0 12px 34px rgba(31,41,51,0.06);}}h1{{margin:0 0 8px 0;font-size:34px;}}h2{{margin:0 0 8px 0;font-size:24px;}}h3{{margin:0 0 8px 0;font-size:16px;}}.sub,.summary{{color:#52606d;}}.status-badge{{display:inline-block;padding:8px 12px;border-radius:999px;font-weight:700;color:{status_style["color"]};background:{status_style["background"]};}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:14px;margin:18px 0;}}.card{{background:#fffdf8;border:1px solid #eadfce;border-radius:16px;padding:14px 16px;}}.label{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7b8794;}}.value{{font-size:28px;font-weight:700;margin-top:8px;}}.dashboard img{{width:100%;border-radius:16px;border:1px solid #eadfce;}}.meta,.badges{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 12px 0;}}.meta span,.badge{{background:#f8f4ec;border:1px solid #eadfce;border-radius:999px;padding:6px 10px;font-size:13px;}}.badge.warning{{background:#fff2d8;color:#9c6500;}}.badge.critical{{background:#fde4e1;color:#9b1c1c;}}table{{width:100%;border-collapse:collapse;background:#fffdf8;border-radius:14px;overflow:hidden;}}th,td{{padding:12px 14px;border-bottom:1px solid #f0e6d6;text-align:left;font-size:14px;}}th{{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#52606d;background:#fbf7f0;}}tbody tr:last-child td{{border-bottom:none;}}.notes-grid{{display:grid;grid-template-columns:repeat(2,minmax(240px,1fr));gap:18px;margin-top:18px;}}ul{{margin:0;padding-left:20px;color:#334e68;}}</style></head><body><div class="hero"><h1>{brief.get("title", "Operations Brief")}</h1><div class="sub"><span class="status-badge">{brief.get("status_display", "")}</span> Generated {brief.get("generated_at_utc", "")} UTC</div><div class="cards">{cards}</div><div class="dashboard"><img src="{dashboard_name}" alt="Dashboard"></div></div>{"".join(sections)}</body></html>'


def _maybe_send_notifications(*, brief: Mapping[str, Any], run_dir: Path, html_path: Path) -> dict[str, Any]:
    config = _load_json_mapping(DEFAULT_NOTIFICATION_CONFIG)
    feishu = dict(config.get("feishu") or {})
    if not feishu or not bool(feishu.get("enabled", True)):
        return {"enabled": False, "reason": "feishu_disabled_or_missing"}
    webhook_url = str(feishu.get("webhook_url") or "").strip()
    if not webhook_url:
        return {"enabled": False, "reason": "feishu_webhook_missing"}
    try:
        response = requests.post(webhook_url, json={"msg_type": "text", "content": {"text": _build_feishu_text(brief, run_dir, html_path)}}, timeout=10)
        response.raise_for_status()
        body = response.json() if response.content else {}
    except Exception as exc:
        return {"enabled": True, "channel": "feishu", "sent": False, "error": str(exc)}
    return {"enabled": True, "channel": "feishu", "sent": bool(body.get("code", 0) == 0), "response": body}


def _build_feishu_text(brief: Mapping[str, Any], run_dir: Path, html_path: Path) -> str:
    summary = dict(brief.get("summary") or {})
    lines = [f"[QSF][{brief.get('phase', '')}] {brief.get('title', '')}", f"状态: {brief.get('status_display', '')}", f"时间(UTC): {brief.get('generated_at_utc', '')}", "总体: 策略 {strategy_count} | 目标 {targets} | 提单 {submitted} | 挂单 {open_orders}".format(strategy_count=summary.get("strategy_count", 0), targets=summary.get("positive_target_count", 0), submitted=summary.get("submitted_count", 0), open_orders=summary.get("open_order_count", 0))]
    for strategy in brief.get("strategies", []):
        top_positions = ", ".join(f"{item.get('symbol', '')} {((_coerce_float(item.get('target_weight')) or 0.0) * 100):.1f}%" for item in list(strategy.get("top_positions") or [])[:3] if item.get("symbol"))
        alerts = ", ".join(str(alert.get("code", "")) for alert in list(strategy.get("alerts") or [])[:2]) or "无"
        lines.append(f"- {strategy.get('strategy_id', '')}: rebalance={strategy.get('rebalance_date') or 'n/a'}, submitted={strategy.get('submitted_count', 0)}, open={strategy.get('open_order_count', 0)}, top={top_positions or 'n/a'}, alerts={alerts}")
    if brief.get("notes"):
        lines.append("备注: " + " | ".join(str(note) for note in brief.get("notes", [])))
    lines.append(f"本地简报: {html_path}")
    lines.append(f"运行目录: {run_dir}")
    return "\n".join(lines)


def _decorate_target(row: Mapping[str, Any], planning_equity: float | None) -> dict[str, Any]:
    metadata = _parse_metadata(row.get("metadata"))
    weight = _coerce_float(row.get("target_weight")) or 0.0
    return {**dict(row), "metadata": metadata, "industry_group": str(metadata.get("industry_group", "") or ""), "planned_notional": (None if planning_equity in (None, 0.0) else weight * float(planning_equity))}


def _metrics_text(strategy: Mapping[str, Any]) -> str:
    account = dict(strategy.get("account") or {})
    summary = dict(strategy.get("source_summary") or {})
    lines = [f"Rebalance: {strategy.get('rebalance_date') or 'n/a'}", f"Targets: {int(strategy.get('positive_target_count', 0))} long / {int(strategy.get('exit_count', 0))} exit"]
    if account.get("equity"):
        lines.append(f"Equity: {account.get('equity', 0.0):,.0f} {account.get('currency', 'USD')}")
    if account.get("cash") is not None:
        lines.append(f"Cash: {float(account.get('cash') or 0.0):,.0f} {account.get('currency', 'USD')}")
    if account.get("buying_power") is not None:
        lines.append(f"Buying Power: {float(account.get('buying_power') or 0.0):,.0f}")
    if account.get("planning_equity") is not None:
        lines.append(f"Planned Capital: {float(account.get('planning_equity') or 0.0):,.0f}")
    if summary.get("annualized_return") is not None:
        lines.append(f"Ann.Return: {float(summary.get('annualized_return') or 0.0) * 100:.1f}%")
    if summary.get("win_rate") is not None:
        lines.append(f"Win Rate: {float(summary.get('win_rate') or 0.0) * 100:.1f}%")
    if strategy.get("alerts"):
        lines.append("Alerts: " + ", ".join(str(alert.get("code", "")) for alert in strategy.get("alerts", [])[:3]))
    return "\n".join(lines)


def _build_summary(strategies: Sequence[Mapping[str, Any]], *, phase: str, status: str) -> dict[str, Any]:
    return {"phase": phase, "status": status, "strategy_count": len(strategies), "positive_target_count": sum(int(item.get("positive_target_count", 0)) for item in strategies), "exit_count": sum(int(item.get("exit_count", 0)) for item in strategies), "submitted_count": sum(int(item.get("submitted_count", 0)) for item in strategies), "open_order_count": sum(int(item.get("open_order_count", 0)) for item in strategies), "alert_counts": dict(Counter(str(alert.get("severity", "info")) for strategy in strategies for alert in strategy.get("alerts", []) if isinstance(alert, Mapping)))}


def _build_next_steps(phase: str, alerts: Sequence[Mapping[str, Any]], positive_target_count: int, submitted_count: int, open_order_count: int) -> list[str]:
    alert_codes = {str(alert.get("code", "")).strip().lower() for alert in alerts}
    steps: list[str] = []
    if phase == "research":
        steps.append("开盘前运行 submit 任务，让 broker 按这份目标仓位提单。" if positive_target_count > 0 else "这轮没有新目标仓位，开盘前先确认是不是数据或风控条件把候选股都过滤掉了。")
    else:
        if submitted_count > 0:
            steps.append("先看 Alpaca paper 的 open orders，确认数量和简报里的 submitted 数一致。")
        if open_order_count > 0:
            steps.append("挂单未成交时，positions 可能暂时还是空的，这属于正常中间态。")
    if "open_orders_lingering" in alert_codes:
        steps.append("如果多轮后挂单仍在，优先检查是否需要等待成交或手动撤单后再重跑。")
    if "data_stale" in alert_codes:
        steps.append("下一轮先补 research 产物，避免继续沿用过期 session 的信号。")
    return (steps or ["当前没有明显阻塞项，按计划等待下一次定时运行即可。"])[:4]


def _build_beginner_notes(phase: str, account: Mapping[str, Any], open_order_count: int, positive_target_count: int, submitted_count: int) -> list[str]:
    notes: list[str] = []
    cash = _coerce_float(account.get("cash"))
    buying_power = _coerce_float(account.get("buying_power"))
    if cash is not None and buying_power is not None and buying_power > cash + 1e-9:
        notes.append("Buying Power 高于 Cash 在 Alpaca paper 很常见，通常是保证金额度，不代表多了真实现金。")
    if phase == "research" and positive_target_count > 0:
        notes.append("Research brief 看到的是计划仓位，不是已经成交的持仓；真正下单要等开盘后的 submit 任务。")
    if phase == "submit" and submitted_count > 0:
        notes.append("Submitted 代表订单已发给 broker；只有状态变成 filled，仓位才算真正成交。")
    if phase == "submit" and open_order_count > 0:
        notes.append("Open Orders 还存在时，账户里的 positions 可能还是空的，这属于成交前的正常中间态。")
    return notes[:4]


def _human_summary(phase: str, strategy_id: str, top_positions: Sequence[Mapping[str, Any]], exit_symbols: Sequence[str], submitted_count: int, open_order_count: int) -> str:
    leaders = ", ".join(f"{item.get('symbol', '')} {((_coerce_float(item.get('target_weight')) or 0.0) * 100):.1f}%" for item in top_positions if item.get("symbol"))
    exits = ", ".join(item for item in exit_symbols if item)
    if phase == "research":
        if leaders and exits:
            return f"{strategy_id} 下一轮更偏向持有 {leaders}，同时退出 {exits}。"
        return f"{strategy_id} 下一轮重点仓位会集中在 {leaders or '暂无'}。"
    if submitted_count > 0:
        return f"{strategy_id} 已经向 paper broker 发出 {submitted_count} 笔订单，其中仍在等待成交的有 {open_order_count} 笔。"
    return f"{strategy_id} 本轮没有新的提单结果。"


def _chart_summary(strategy: Mapping[str, Any]) -> str:
    leaders = ", ".join(f"{item.get('symbol', '')} {((_coerce_float(item.get('target_weight')) or 0.0) * 100):.0f}%" for item in list(strategy.get("top_positions") or [])[:3] if item.get("symbol"))
    return f"Orders sent: {int(strategy.get('submitted_count', 0))}; still open: {int(strategy.get('open_order_count', 0))}." if strategy.get("phase") == "submit" else f"Top planned holdings: {leaders or 'n/a'}."


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
