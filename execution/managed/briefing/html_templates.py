from __future__ import annotations

from html import escape
from typing import Any, Mapping

from execution.managed.briefing.presenter import format_generated_time_cn, strategy_cn_name


A4_WIDTH_PX = 1240
A4_HEIGHT_PX = 1754

PHASE_SUBTITLE = {
    "research": "夜间研究简报｜图表为主，聚焦仓位与预测",
    "submit": "开盘执行简报｜图表为主，聚焦仓位与盈亏",
}


def render_brief_html(*, brief: Mapping[str, Any], chart_payload: Mapping[str, Any]) -> str:
    phase = str(brief.get("phase") or "")
    if phase == "research":
        return render_research_html(brief=brief, chart_payload=chart_payload)
    if phase == "submit":
        return render_submit_html(brief=brief, chart_payload=chart_payload)
    return render_research_html(brief=brief, chart_payload=chart_payload)


def render_research_html(*, brief: Mapping[str, Any], chart_payload: Mapping[str, Any]) -> str:
    strategies = _build_strategy_cards(chart_payload=chart_payload, phase="research")
    return _wrap_page(brief=brief, phase="research", strategy_cards_html="\n".join(strategies))


def render_submit_html(*, brief: Mapping[str, Any], chart_payload: Mapping[str, Any]) -> str:
    strategies = _build_strategy_cards(chart_payload=chart_payload, phase="submit")
    return _wrap_page(brief=brief, phase="submit", strategy_cards_html="\n".join(strategies))


def _wrap_page(*, brief: Mapping[str, Any], phase: str, strategy_cards_html: str) -> str:
    summary = dict(brief.get("summary") or {})
    title = _escape(str(brief.get("title") or "运行简报"))
    status_display = _escape(str(brief.get("status_display") or ""))
    generated_at = _escape(format_generated_time_cn(str(brief.get("generated_at_utc") or "")) or str(brief.get("generated_at_utc") or ""))
    subtitle = _escape(PHASE_SUBTITLE.get(phase, "策略运行简报"))
    cards = "".join(
        [
            _metric_card("策略数", str(summary.get("strategy_count", 0))),
            _metric_card("目标仓位", str(summary.get("positive_target_count", 0))),
            _metric_card("已提订单", str(summary.get("submitted_count", 0))),
            _metric_card("未完成挂单", str(summary.get("open_order_count", 0))),
        ]
    )
    notes = [str(item).strip() for item in list(brief.get("notes") or []) if str(item).strip()]
    note_html = f'<div class="note-line">备注：{_escape("；".join(notes))}</div>' if notes else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #eef3f8;
      --page-bg: #f8fafc;
      --ink: #102a43;
      --muted: #4f6274;
      --line: #dbe4ee;
      --card: #ffffff;
      --chip-bg: #f3f7fc;
      --ok-bg: #dff3ea;
      --ok-ink: #0b6e4f;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      background: radial-gradient(1200px 800px at 92% -12%, #dae5f3 0%, #eef3f8 45%, #e7eef8 100%);
      color: var(--ink);
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
    }}
    .page {{
      width: {A4_WIDTH_PX}px;
      height: {A4_HEIGHT_PX}px;
      margin: 0 auto;
      padding: 20px 22px 18px;
      background: linear-gradient(180deg, #fdfefe 0%, var(--page-bg) 100%);
      display: grid;
      grid-template-rows: 158px 1fr;
      gap: 14px;
      overflow: hidden;
    }}
    .hero {{
      background: linear-gradient(115deg, #102a43 0%, #1f3d5a 58%, #28587b 100%);
      border: 1px solid #20425f;
      border-radius: 20px;
      padding: 14px 16px;
      color: #f8fbff;
      display: grid;
      grid-template-rows: auto auto auto;
      gap: 8px;
    }}
    .hero-top {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 14px;
    }}
    .title {{
      font-size: 28px;
      font-weight: 800;
      line-height: 1.15;
      letter-spacing: 0.2px;
    }}
    .subtitle {{
      font-size: 13px;
      color: #dbe8f5;
      margin-top: 3px;
    }}
    .status {{
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 700;
      background: var(--ok-bg);
      color: var(--ok-ink);
      white-space: nowrap;
    }}
    .meta {{
      font-size: 12px;
      color: #c6daee;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
    }}
    .metric {{
      background: rgba(255, 255, 255, 0.12);
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 12px;
      padding: 8px 10px;
    }}
    .metric-label {{
      font-size: 11px;
      color: #dbe8f5;
      letter-spacing: 0.08em;
    }}
    .metric-value {{
      margin-top: 2px;
      font-size: 20px;
      font-weight: 800;
      color: #ffffff;
    }}
    .note-line {{
      margin-top: 2px;
      font-size: 11px;
      color: #d7e7f8;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .stack {{
      display: grid;
      grid-template-rows: 1fr 1fr;
      gap: 12px;
      min-height: 0;
    }}
    .strategy {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 12px 12px 10px;
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      gap: 8px;
      min-height: 0;
      overflow: hidden;
    }}
    .strategy-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
    }}
    .strategy-title {{
      font-size: 18px;
      font-weight: 800;
      line-height: 1.2;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .strategy-date {{
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .chip {{
      font-size: 11px;
      color: #37506a;
      background: var(--chip-bg);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 8px;
    }}
    .chart-grid {{
      min-height: 0;
      display: grid;
      gap: 8px;
    }}
    .research-grid {{
      grid-template-columns: 0.95fr 1.15fr 1.15fr;
      align-items: start;
    }}
    .research-grid .chart-card {{
      grid-template-rows: auto auto;
    }}
    .research-grid .chart-card img {{
      height: auto;
      aspect-ratio: 16 / 10;
      object-fit: contain;
    }}
    .submit-grid {{
      grid-template-columns: 0.95fr 1.05fr 1.1fr;
    }}
    .submit-grid .dist {{
      grid-column: 1;
      grid-row: 1;
    }}
    .submit-grid .total {{
      grid-column: 2;
      grid-row: 1;
    }}
    .submit-grid .symbol {{
      grid-column: 3;
      grid-row: 1;
    }}
    .chart-card {{
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fdfefe;
      display: grid;
      grid-template-rows: 1fr auto;
      overflow: hidden;
      min-height: 0;
    }}
    .chart-card img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #f6f9fd;
      display: block;
    }}
    .chart-card figcaption {{
      padding: 4px 8px 5px;
      font-size: 11px;
      color: var(--muted);
      line-height: 1.25;
      border-top: 1px solid #eaf0f7;
      background: #fcfefe;
      white-space: normal;
      overflow: hidden;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
    }}
    .strategy-overview {{
      margin: 0;
      font-size: 12px;
      line-height: 1.45;
      color: #2f455c;
      background: #f8fbff;
      border: 1px solid #dce8f5;
      border-radius: 10px;
      padding: 6px 8px;
      overflow: hidden;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
    }}
    .summary-line {{
      font-size: 12px;
      color: #2f455c;
      background: #f3f8fd;
      border: 1px solid #d8e5f2;
      border-radius: 10px;
      padding: 5px 8px;
      white-space: normal;
      overflow: hidden;
      line-height: 1.35;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
    }}
    .strategy.empty {{
      align-items: center;
      justify-items: center;
      text-align: center;
      color: var(--muted);
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-top">
        <div>
          <div class="title">{title}</div>
          <div class="subtitle">{subtitle}</div>
        </div>
        <div class="status">{status_display}</div>
      </div>
      <div class="meta">北京时间 {generated_at}</div>
      <div class="metrics">{cards}</div>
      {note_html}
    </section>
    <section class="stack">
      {strategy_cards_html}
    </section>
  </main>
</body>
</html>
"""


def _build_strategy_cards(*, chart_payload: Mapping[str, Any], phase: str) -> list[str]:
    entries = [dict(item) for item in list(chart_payload.get("strategies") or []) if isinstance(item, Mapping)]
    cards: list[str] = []
    for entry in entries[:2]:
        cards.append(_strategy_card(entry=entry, phase=phase))
    while len(cards) < 2:
        cards.append('<article class="strategy empty"><div>暂无策略数据</div></article>')
    return cards


def _strategy_card(*, entry: Mapping[str, Any], phase: str) -> str:
    strategy_id = str(entry.get("strategy_id") or "")
    fallback_name = str(entry.get("strategy_name") or strategy_id or "未命名策略")
    title = _escape(strategy_cn_name(strategy_id, fallback=fallback_name))
    date_text = _escape(str(entry.get("rebalance_date") or "n/a"))
    top_positions = _escape(str(entry.get("top_positions_text") or "暂无重点仓位"))
    charts = dict(entry.get("charts") or {})
    chart_explanations = dict(entry.get("chart_explanations") or {})
    if phase == "research":
        agreement = float(entry.get("agreement_ratio") or 0.0) * 100.0
        chips = "".join(
            [
                _chip(f"重点仓位：{top_positions}"),
                _chip(f"专家一致性：{agreement:.0f}%"),
            ]
        )
        conclusion = _short_text(
            str(entry.get("research_conclusion") or ""),
            fallback=str(entry.get("explain_like_human") or "暂无结论"),
            max_len=190,
        )
        chart_grid = f"""
        <div class="chart-grid research-grid">
          {_chart_card(charts.get("allocation_pie", ""), "股票池仓位分布", chart_explanations.get("allocation_pie", ""))}
          {_chart_card(charts.get("pool_curve", ""), "股票池曲线", chart_explanations.get("pool_curve", ""))}
          {_chart_card(charts.get("expert_compare", ""), "Expert 与 Voting 对比", chart_explanations.get("expert_compare", ""))}
        </div>
        """
        summary_line = f"结论：{_escape(conclusion)}"
    else:
        submitted = int(entry.get("submitted_count") or 0)
        open_count = int(entry.get("open_order_count") or 0)
        chips = "".join(
            [
                _chip(f"重点仓位：{top_positions}"),
                _chip(f"已提订单：{submitted}"),
                _chip(f"未完成挂单：{open_count}"),
            ]
        )
        chart_grid = f"""
        <div class="chart-grid submit-grid">
          <div class="dist">{_chart_card(charts.get("current_distribution_pie", ""), "当前账户持仓分布（含现金）", chart_explanations.get("current_distribution_pie", ""))}</div>
          <div class="total">{_chart_card(charts.get("total_pnl_curve", ""), "账户权益曲线（现金+持仓）", chart_explanations.get("total_pnl_curve", ""))}</div>
          <div class="symbol">{_chart_card(charts.get("signal_strength", ""), "单股信号强度（归一分位）", chart_explanations.get("signal_strength", ""))}</div>
        </div>
        """
        alerts = [dict(item) for item in list(entry.get("alerts") or []) if isinstance(item, Mapping)]
        alert_text = "；".join(str(item.get("title") or item.get("code") or "") for item in alerts[:2]) or "当前无告警"
        summary_line = f"提示：{_escape(alert_text)}"
    return f"""
    <article class="strategy">
      <header class="strategy-head">
        <div class="strategy-title">{title}</div>
        <div class="strategy-date">调仓日：{date_text}</div>
      </header>
      <div class="chips">{chips}</div>
      {chart_grid}
      <div class="summary-line">{summary_line}</div>
    </article>
    """


def _chart_card(path: str, title: str, description: str) -> str:
    safe_path = _escape(str(path or ""))
    safe_title = _escape(title)
    safe_description = _escape(description) if str(description or "").strip() else ""
    caption = safe_title if not safe_description else f"{safe_title}：{safe_description}"
    return f'<figure class="chart-card"><img src="{safe_path}" alt="{safe_title}"><figcaption>{caption}</figcaption></figure>'


def _metric_card(label: str, value: str) -> str:
    return f'<div class="metric"><div class="metric-label">{_escape(label)}</div><div class="metric-value">{_escape(value)}</div></div>'


def _chip(value: str) -> str:
    return f'<span class="chip">{_escape(value)}</span>'


def _short_text(value: str, *, fallback: str, max_len: int = 90) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if len(text) <= max_len:
        return text
    return text[: max(1, max_len - 1)] + "…"


def _escape(value: Any) -> str:
    return escape(str(value or ""))


__all__ = [
    "A4_WIDTH_PX",
    "A4_HEIGHT_PX",
    "render_brief_html",
    "render_research_html",
    "render_submit_html",
]
