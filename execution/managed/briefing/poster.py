from __future__ import annotations

import math
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

from execution.managed.briefing.presenter import format_generated_time_cn, strategy_cn_name


A4_PORTRAIT = (8.27, 11.69)

BG = "#f5efe4"
CARD = "#fffdf8"
INK = "#102033"
MUTED = "#556579"
LINE = "#d9e2ec"
HEADER = "#102a43"
HEADER_ACCENT = "#0b6e4f"
SUBTLE = "#f1f5f9"

STATUS_STYLES = {
    "success": {"label": "运行正常", "color": "#0b6e4f", "background": "#dff3ea"},
    "partial": {"label": "需要关注", "color": "#9c6500", "background": "#fff2d8"},
    "failed": {"label": "运行失败", "color": "#9b1c1c", "background": "#fde4e1"},
}

PIE_COLORS = ["#0b6e4f", "#1b998b", "#457b9d", "#ffb703", "#e76f51", "#8ecae6", "#adb5bd"]
BAR_COLORS = {
    "lightgbm": "#457b9d",
    "xgboost": "#2a9d8f",
    "catboost": "#e76f51",
    "lstm": "#e9c46a",
    "transformer": "#8ecae6",
    "ensemble": "#0b6e4f",
}


def render_operation_brief_poster(*, brief: Mapping[str, Any], output_path) -> None:
    phase = str(brief.get("phase") or "")
    if phase == "research":
        _render_research_poster(brief=brief, output_path=output_path)
        return
    if phase == "submit":
        _render_submit_poster(brief=brief, output_path=output_path)
        return
    _render_fallback_poster(brief=brief, output_path=output_path)


def _render_research_poster(*, brief: Mapping[str, Any], output_path) -> None:
    fig = _make_figure(brief, accent=HEADER_ACCENT)
    _draw_header(fig, brief, subtitle="研究模板 | 仓位分布、股票池曲线、expert/voting 对比")
    _draw_summary_row(fig, brief, phase="research")

    strategies = list(brief.get("strategies") or [])[:2]
    _draw_strategy_cards(
        fig,
        brief,
        strategies,
        phase="research",
        card_builder=_build_research_card,
    )

    _save_figure(fig, output_path)


def _render_submit_poster(*, brief: Mapping[str, Any], output_path) -> None:
    fig = _make_figure(brief, accent="#1d3557")
    _draw_header(fig, brief, subtitle="执行模板 | 当前账户持仓、账户权益曲线、单股信号强度")
    _draw_summary_row(fig, brief, phase="submit")

    strategies = list(brief.get("strategies") or [])[:2]
    _draw_strategy_cards(
        fig,
        brief,
        strategies,
        phase="submit",
        card_builder=_build_submit_card,
    )

    _save_figure(fig, output_path)


def _render_fallback_poster(*, brief: Mapping[str, Any], output_path) -> None:
    fig = _make_figure(brief, accent=HEADER_ACCENT)
    ax = fig.add_axes([0.06, 0.18, 0.88, 0.62])
    _style_panel(ax)
    ax.axis("off")
    ax.text(0.5, 0.62, str(brief.get("title") or "运行简报"), ha="center", va="center", fontsize=24, fontweight="bold", color=INK)
    ax.text(0.5, 0.48, "未知简报阶段，无法渲染海报模板。", ha="center", va="center", fontsize=12, color=MUTED)
    _save_figure(fig, output_path)


def _make_figure(brief: Mapping[str, Any], *, accent: str) -> plt.Figure:
    fig = plt.figure(figsize=A4_PORTRAIT)
    fig.patch.set_facecolor(BG)
    fig.add_artist(Circle((0.92, 0.14), 0.18, transform=fig.transFigure, facecolor=accent, edgecolor="none", alpha=0.06, zorder=0))
    fig.add_artist(Circle((0.08, 0.82), 0.12, transform=fig.transFigure, facecolor="#8ecae6", edgecolor="none", alpha=0.08, zorder=0))
    fig.add_artist(Rectangle((0.0, 0.92), 1.0, 0.08, transform=fig.transFigure, facecolor=HEADER, edgecolor="none", alpha=0.98, zorder=0))
    fig.add_artist(Rectangle((0.0, 0.0), 1.0, 0.015, transform=fig.transFigure, facecolor=accent, edgecolor="none", alpha=0.95, zorder=0))
    return fig


def _draw_header(fig: plt.Figure, brief: Mapping[str, Any], *, subtitle: str) -> None:
    title = str(brief.get("title") or "运行简报")
    generated_at = format_generated_time_cn(str(brief.get("generated_at_utc") or "")) or str(brief.get("generated_at_utc") or "")
    status_style = STATUS_STYLES.get(str(brief.get("status") or "success"), STATUS_STYLES["success"])
    summary = dict(brief.get("summary") or {})

    fig.text(0.055, 0.965, title, ha="left", va="center", fontsize=22, fontweight="bold", color="white")
    fig.text(0.055, 0.935, subtitle, ha="left", va="center", fontsize=9.5, color="#d5e2ef")
    fig.text(
        0.945,
        0.965,
        f"{status_style['label']}",
        ha="right",
        va="center",
        fontsize=10.5,
        fontweight="bold",
        color=status_style["color"],
        bbox={"boxstyle": "round,pad=0.34", "facecolor": status_style["background"], "edgecolor": status_style["background"]},
    )
    fig.text(
        0.945,
        0.935,
        f"北京时间 {generated_at}",
        ha="right",
        va="center",
        fontsize=9.2,
        color="#d5e2ef",
    )
    fig.text(
        0.945,
        0.914,
        f"策略 {summary.get('strategy_count', 0)}  |  目标 {summary.get('positive_target_count', 0)}  |  已提 {summary.get('submitted_count', 0)}  |  未完成 {summary.get('open_order_count', 0)}",
        ha="right",
        va="center",
        fontsize=8.8,
        color="#d5e2ef",
    )


def _draw_summary_row(fig: plt.Figure, brief: Mapping[str, Any], *, phase: str) -> None:
    cards = _summary_cards(brief, phase=phase)
    left = 0.045
    gap = 0.017
    width = (0.91 - gap * (len(cards) - 1)) / max(1, len(cards))
    y = 0.815
    h = 0.075
    for index, (label, value, accent) in enumerate(cards):
        x = left + index * (width + gap)
        patch = FancyBboxPatch(
            (x, y),
            width,
            h,
            boxstyle="round,pad=0.012,rounding_size=0.018",
            transform=fig.transFigure,
            facecolor=CARD,
            edgecolor=LINE,
            linewidth=1.0,
            zorder=1,
        )
        fig.add_artist(patch)
        fig.add_artist(Rectangle((x, y + h - 0.012), width, 0.012, transform=fig.transFigure, facecolor=accent, edgecolor="none", zorder=2))
        fig.text(x + 0.015, y + 0.048, label, ha="left", va="center", fontsize=8.5, color="#6b7c8f")
        fig.text(x + 0.015, y + 0.022, value, ha="left", va="center", fontsize=15, fontweight="bold", color=INK)


def _draw_strategy_cards(
    fig: plt.Figure,
    brief: Mapping[str, Any],
    strategies: Sequence[Mapping[str, Any]],
    *,
    phase: str,
    card_builder,
) -> None:
    if not strategies:
        ax = fig.add_axes([0.06, 0.09, 0.88, 0.68])
        _style_panel(ax)
        ax.axis("off")
        ax.text(0.5, 0.5, "无策略数据", ha="center", va="center", fontsize=14, color=MUTED)
        return

    top = 0.78
    bottom = 0.065
    gap = 0.024 if len(strategies) > 1 else 0.0
    card_height = (top - bottom - gap * (len(strategies) - 1)) / len(strategies)

    for index, strategy in enumerate(strategies):
        y0 = top - (index + 1) * card_height - index * gap
        bbox = (0.045, y0, 0.91, card_height)
        _draw_card_background(fig, bbox, accent=HEADER_ACCENT if phase == "research" else "#1d3557")
        card_builder(fig, strategy, bbox=bbox, index=index, total=len(strategies), brief=brief)


def _draw_card_background(fig: plt.Figure, bbox: tuple[float, float, float, float], *, accent: str) -> None:
    x, y, w, h = bbox
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.024",
        transform=fig.transFigure,
        facecolor=CARD,
        edgecolor=LINE,
        linewidth=1.0,
        zorder=0.5,
    )
    fig.add_artist(patch)
    fig.add_artist(Rectangle((x, y + h - 0.01), w, 0.01, transform=fig.transFigure, facecolor=accent, edgecolor="none", alpha=0.95, zorder=1))


def _build_research_card(fig: plt.Figure, strategy: Mapping[str, Any], *, bbox: tuple[float, float, float, float], index: int, total: int, brief: Mapping[str, Any]) -> None:
    x, y, w, h = bbox
    title = _strategy_label(strategy)
    agreement = _agreement_ratio(strategy) * 100.0
    top_weight = _top_weight(strategy) * 100.0
    pill = f"一致性 {agreement:.0f}%  |  核心 {top_weight:.1f}%"
    _draw_card_title(fig, x, y, w, h, title, pill=pill, accent=HEADER_ACCENT)

    inner = fig.add_gridspec(
        1,
        3,
        left=x + 0.018,
        right=x + w - 0.018,
        bottom=y + 0.020,
        top=y + h - 0.052,
        wspace=0.16,
        width_ratios=[1.08, 1.18, 1.02],
    )
    ax_left = fig.add_subplot(inner[0, 0])
    ax_mid = fig.add_subplot(inner[0, 1])
    ax_right = fig.add_subplot(inner[0, 2])
    _draw_research_allocation(ax_left, strategy)
    _draw_research_curve(ax_mid, strategy)
    _draw_research_expert_compare(ax_right, strategy)


def _build_submit_card(fig: plt.Figure, strategy: Mapping[str, Any], *, bbox: tuple[float, float, float, float], index: int, total: int, brief: Mapping[str, Any]) -> None:
    x, y, w, h = bbox
    title = _strategy_label(strategy)
    submitted = int(_coerce_int(strategy.get("submitted_count")) or 0)
    open_orders = int(_coerce_int(strategy.get("open_order_count")) or 0)
    pill = f"已提 {submitted} 笔  |  未完成 {open_orders} 笔"
    _draw_card_title(fig, x, y, w, h, title, pill=pill, accent="#1d3557")

    inner = fig.add_gridspec(
        1,
        3,
        left=x + 0.018,
        right=x + w - 0.018,
        bottom=y + 0.020,
        top=y + h - 0.052,
        wspace=0.18,
        width_ratios=[1.0, 1.18, 1.05],
    )
    ax_left = fig.add_subplot(inner[0, 0])
    ax_mid = fig.add_subplot(inner[0, 1])
    ax_right = fig.add_subplot(inner[0, 2])
    _draw_submit_distribution(ax_left, strategy)
    _draw_submit_total_curve(ax_mid, strategy)
    _draw_submit_signal_strength(ax_right, strategy)


def _draw_card_title(fig: plt.Figure, x: float, y: float, w: float, h: float, title: str, *, pill: str, accent: str) -> None:
    fig.text(x + 0.016, y + h - 0.025, title, ha="left", va="center", fontsize=11.5, fontweight="bold", color=INK)
    fig.text(
        x + w - 0.016,
        y + h - 0.025,
        pill,
        ha="right",
        va="center",
        fontsize=8.8,
        color=accent,
        bbox={"boxstyle": "round,pad=0.28", "facecolor": SUBTLE, "edgecolor": SUBTLE},
    )


def _style_panel(ax: Any) -> None:
    ax.set_facecolor(CARD)
    for spine in ax.spines.values():
        spine.set_color(LINE)
        spine.set_linewidth(0.9)
    ax.tick_params(colors="#4f6274", labelsize=8)


def _draw_research_allocation(ax: Any, strategy: Mapping[str, Any]) -> None:
    items = _compact_slice_items(list(strategy.get("top_positions") or []), label_key="symbol", value_key="target_weight", max_items=5, other_label="其他")
    if not items:
        ax.axis("off")
        ax.text(0.5, 0.5, "暂无目标仓位", ha="center", va="center", fontsize=11.5, color=MUTED)
        return
    labels, values = zip(*items)
    values_pct = [max(0.0, _coerce_float(value) or 0.0) for value in values]
    total = sum(values_pct)
    if total <= 0:
        ax.axis("off")
        ax.text(0.5, 0.5, "暂无目标仓位", ha="center", va="center", fontsize=11.5, color=MUTED)
        return
    ax.pie(
        values_pct,
        labels=list(labels),
        colors=PIE_COLORS[: len(values_pct)],
        startangle=110,
        counterclock=False,
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 7 else "",
        pctdistance=0.73,
        labeldistance=1.05,
        wedgeprops={"width": 0.45, "edgecolor": "white"},
        textprops={"fontsize": 8.2, "color": INK},
    )
    ax.add_artist(Circle((0, 0), 0.47, facecolor=CARD, edgecolor="none", zorder=0))
    ax.set_aspect("equal")
    ax.set_title("仓位分布", fontsize=10.5, fontweight="bold", color=INK, loc="left", pad=10)
    ax.text(0.0, -1.20, _chart_leaders_text(strategy), ha="center", va="center", fontsize=8.6, color=MUTED, transform=ax.transData)
    ax.set_xticks([])
    ax.set_yticks([])


def _draw_research_curve(ax: Any, strategy: Mapping[str, Any]) -> None:
    curves = dict(strategy.get("research_curves") or {})
    if not curves:
        ax.axis("off")
        ax.text(0.5, 0.5, "暂无股票池曲线", ha="center", va="center", fontsize=11.5, color=MUTED)
        return
    plotted = 0
    for symbol, points in curves.items():
        points_list = [dict(item) for item in points if isinstance(item, Mapping)]
        if len(points_list) < 2:
            continue
        xs = list(range(len(points_list)))
        ys = [(_coerce_float(item.get("normalized_close")) or 1.0) * 100.0 for item in points_list]
        ax.plot(xs, ys, linewidth=2.0, label=str(symbol))
        plotted += 1
    if plotted == 0:
        ax.axis("off")
        ax.text(0.5, 0.5, "暂无股票池曲线", ha="center", va="center", fontsize=11.5, color=MUTED)
        return
    ax.set_title("股票池曲线", fontsize=10.5, fontweight="bold", color=INK, loc="left", pad=10)
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylabel("首日 = 100", color=MUTED, fontsize=8.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", fontsize=7.5, frameon=False, ncol=2)
    first_points = next(iter(curves.values()))
    first_points_list = [dict(item) for item in first_points if isinstance(item, Mapping)]
    if first_points_list:
        start = str(first_points_list[0].get("date") or "")
        end = str(first_points_list[-1].get("date") or "")
        ax.text(0.02, 0.96, f"{start} → {end}", transform=ax.transAxes, ha="left", va="top", fontsize=8.2, color=MUTED)
    conclusion = str(strategy.get("research_conclusion") or "")
    if conclusion:
        ax.text(
            0.02,
            0.02,
            conclusion,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.2,
            color=INK,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "#f8fafc", "edgecolor": LINE},
        )


def _draw_research_expert_compare(ax: Any, strategy: Mapping[str, Any]) -> None:
    snapshot = dict(strategy.get("expert_snapshot") or {})
    symbols = [str(item).upper().strip() for item in list(snapshot.get("symbols") or []) if str(item).strip()]
    experts = [str(item).strip() for item in list(snapshot.get("experts") or []) if str(item).strip()]
    score_map = snapshot.get("scores")
    if not symbols or not experts or not isinstance(score_map, Mapping):
        ax.axis("off")
        ax.text(0.5, 0.5, "暂无 expert / voting 快照", ha="center", va="center", fontsize=11.5, color=MUTED)
        return

    width = max(0.10, 0.78 / max(1, len(experts)))
    x_base = list(range(len(symbols)))
    has_value = False
    for index, expert in enumerate(experts):
        expert_values = score_map.get(expert) if isinstance(score_map.get(expert), Mapping) else {}
        values = []
        for symbol in symbols:
            value = _coerce_float(expert_values.get(symbol))
            if value is None:
                value = 0.0
            else:
                has_value = True
            values.append(value)
        offset = (index - (len(experts) - 1) / 2.0) * width
        xs = [item + offset for item in x_base]
        color = BAR_COLORS.get(_normalize(expert), "#64748b")
        ax.bar(xs, values, width=width * 0.9, label=_display_expert_name(expert), color=color, alpha=0.92 if _normalize(expert) == "ensemble" else 0.8)

    if not has_value:
        ax.axis("off")
        ax.text(0.5, 0.5, "专家预测为空", ha="center", va="center", fontsize=11.5, color=MUTED)
        return

    ax.axhline(0.0, color="#8fa3b5", linewidth=1.0, linestyle="--")
    limit = max(0.05, max(abs(_coerce_float(value) or 0.0) for expert in score_map.values() if isinstance(expert, Mapping) for value in expert.values()))
    ax.set_ylim(-limit * 1.25, limit * 1.25)
    ax.set_xticks(x_base)
    ax.set_xticklabels(symbols, fontsize=8.0)
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_title("expert / voting 对比", fontsize=10.5, fontweight="bold", color=INK, loc="left", pad=10)
    ax.set_ylabel("信号值", color=MUTED, fontsize=8.5)
    ax.legend(loc="upper left", fontsize=7.2, frameon=False, ncol=3)
    asof = str(snapshot.get("asof_date") or "")
    if asof:
        ax.text(0.02, 0.96, f"快照 {asof}", transform=ax.transAxes, ha="left", va="top", fontsize=8.2, color=MUTED)


def _draw_submit_distribution(ax: Any, strategy: Mapping[str, Any]) -> None:
    distribution = _compact_slice_items(list(strategy.get("current_distribution") or []), label_key="label", value_key="value", max_items=6, other_label="其他")
    if not distribution:
        ax.axis("off")
        ax.text(0.5, 0.5, "暂无当前账户持仓", ha="center", va="center", fontsize=11.5, color=MUTED)
        return
    labels, values = zip(*distribution)
    values_num = [max(0.0, _coerce_float(item) or 0.0) for item in values]
    total = sum(values_num)
    if total <= 0:
        ax.axis("off")
        ax.text(0.5, 0.5, "暂无当前账户持仓", ha="center", va="center", fontsize=11.5, color=MUTED)
        return
    ax.pie(
        values_num,
        labels=list(labels),
        colors=PIE_COLORS[: len(values_num)],
        startangle=110,
        counterclock=False,
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 7 else "",
        pctdistance=0.72,
        labeldistance=1.05,
        wedgeprops={"width": 0.45, "edgecolor": "white"},
        textprops={"fontsize": 8.1, "color": INK},
    )
    ax.add_artist(Circle((0, 0), 0.47, facecolor=CARD, edgecolor="none", zorder=0))
    ax.set_aspect("equal")
    ax.set_title("当前账户持仓分布（含现金）", fontsize=10.5, fontweight="bold", color=INK, loc="left", pad=10)
    currency = str((strategy.get("account") or {}).get("currency") or "USD")
    ax.text(0.0, -1.20, f"总额 {total:,.0f} {currency}", ha="center", va="center", fontsize=8.6, color=MUTED, transform=ax.transData)
    ax.set_xticks([])
    ax.set_yticks([])


def _draw_submit_total_curve(ax: Any, strategy: Mapping[str, Any]) -> None:
    curve = [dict(item) for item in list(strategy.get("equity_curve") or []) if isinstance(item, Mapping)]
    if not curve:
        ax.axis("off")
        ax.text(0.5, 0.5, "账户权益曲线样本不足", ha="center", va="center", fontsize=11.5, color=MUTED)
        return
    parsed_times = [
        _parse_iso_datetime(item.get("timestamp_utc")) or _parse_iso_date(item.get("date"))
        for item in curve
    ]
    use_date_axis = all(value is not None for value in parsed_times)
    xs = parsed_times if use_date_axis else list(range(len(curve)))
    ys = [(_coerce_float(item.get("pnl_pct")) or 0.0) * 100.0 for item in curve]
    equity_values = [_coerce_float(item.get("equity")) for item in curve]
    has_equity_values = all(value is not None for value in equity_values)
    if has_equity_values and equity_values:
        ys = [float(item or 0.0) for item in equity_values]
        currency = str((strategy.get("account") or {}).get("currency") or "USD")
        ax.set_ylabel(f"账户权益 ({currency})", color=MUTED, fontsize=8.5)
        ax.fill_between(xs, ys, ys[0] if ys else 0.0, color="#a8dadc", alpha=0.22)
    else:
        ax.set_ylabel("累计收益 (%)", color=MUTED, fontsize=8.5)
        ax.fill_between(xs, ys, 0.0, color="#a8dadc", alpha=0.26)
        ax.axhline(0.0, color="#8fa3b5", linewidth=1.0, linestyle="--")
    ax.plot(xs, ys, color="#1d3557", linewidth=2.2, marker="o", markersize=3.0)
    if use_date_axis:
        day_values = {value.date() for value in parsed_times if value is not None}
        if len(curve) == 1:
            x0 = parsed_times[0]
            ax.set_xlim(x0 - timedelta(hours=12), x0 + timedelta(hours=12))
            ax.set_xticks([x0])
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
            ax.set_xlabel("日期", color=MUTED, fontsize=8.2)
        else:
            if len(day_values) > 1:
                tick_positions: list[datetime] = []
                seen_days: set[datetime.date] = set()
                for value in parsed_times:
                    if value is None:
                        continue
                    day = value.date()
                    if day in seen_days:
                        continue
                    seen_days.add(day)
                    tick_positions.append(value)
                if tick_positions:
                    ax.set_xticks(tick_positions)
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
                ax.set_xlabel("日期", color=MUTED, fontsize=8.2)
            else:
                tick_positions = [value for value in parsed_times if value is not None]
                if tick_positions:
                    unique_ticks: list[datetime] = []
                    seen: set[datetime] = set()
                    for value in tick_positions:
                        if value in seen:
                            continue
                        seen.add(value)
                        unique_ticks.append(value)
                    ax.set_xticks(unique_ticks)
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
                ax.set_xlabel("时间", color=MUTED, fontsize=8.2)
        ax.tick_params(axis="x", labelsize=7.5)
    else:
        ax.set_xlabel("样本序号", color=MUTED, fontsize=8.2)
    ax.set_title("账户权益曲线（现金+持仓）", fontsize=10.2, fontweight="bold", color=INK, loc="left", pad=8)
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    first = str(curve[0].get("date") or "")
    last = str(curve[-1].get("date") or "")
    ax.text(0.02, 0.96, f"{first} → {last}", transform=ax.transAxes, ha="left", va="top", fontsize=8.2, color=MUTED)


def _draw_submit_signal_strength(ax: Any, strategy: Mapping[str, Any]) -> None:
    top_positions = [dict(item) for item in list(strategy.get("top_positions") or []) if isinstance(item, Mapping)]
    ranked = sorted(
        top_positions,
        key=lambda item: _coerce_float(item.get("target_weight")) or 0.0,
        reverse=True,
    )
    ranked = [item for item in ranked if str(item.get("symbol") or "").strip()][:6]
    if not ranked:
        _draw_submit_symbol_proxy(ax, strategy)
        return

    symbols = [str(item.get("symbol") or "").upper().strip() for item in ranked]
    raw_scores = [_coerce_float(item.get("score")) for item in ranked]
    if all(value is None for value in raw_scores):
        _draw_submit_symbol_proxy(ax, strategy)
        return

    score_values = [float(value or 0.0) for value in raw_scores]
    percentiles = _to_percentiles(score_values)
    bars = ax.bar(symbols, percentiles, color=PIE_COLORS[: len(symbols)], alpha=0.9, label="信号分位")
    for bar, value in zip(bars, percentiles):
        ax.text(bar.get_x() + bar.get_width() / 2.0, value + 1.8, f"{value:.0f}", ha="center", va="bottom", fontsize=7.8, color=MUTED)

    confidence_raw = [_coerce_float(item.get("confidence")) for item in ranked]
    confidence_values: list[float] = []
    has_confidence = False
    for value in confidence_raw:
        if value is None:
            confidence_values.append(0.0)
            continue
        has_confidence = True
        scaled = value * 100.0 if abs(value) <= 1.0 else value
        confidence_values.append(max(0.0, min(100.0, scaled)))
    if has_confidence:
        ax.plot(symbols, confidence_values, color="#0b6e4f", linewidth=1.8, marker="o", markersize=4.0, label="置信度")

    ax.axhline(50.0, color="#8fa3b5", linewidth=1.0, linestyle="--")
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylim(0.0, 100.0)
    ax.set_ylabel("相对分位 (0-100)", color=MUTED, fontsize=8.5)
    ax.set_title("单股信号强度（归一分位）", fontsize=10.2, fontweight="bold", color=INK, loc="left", pad=8)
    note = "柱为入选个股 score 的相对分位；折线为 confidence（若有）。" if has_confidence else "柱为入选个股 score 的相对分位（0-100）。"
    ax.text(0.02, 0.02, note, transform=ax.transAxes, ha="left", va="bottom", fontsize=8.0, color=MUTED)
    if has_confidence:
        ax.legend(loc="upper left", fontsize=7.2, frameon=False)


def _draw_submit_symbol_curve(ax: Any, strategy: Mapping[str, Any]) -> None:
    # Legacy alias kept for older callers.
    _draw_submit_signal_strength(ax, strategy)


def _draw_submit_symbol_proxy(ax: Any, strategy: Mapping[str, Any]) -> None:
    top_positions = [dict(item) for item in list(strategy.get("top_positions") or []) if isinstance(item, Mapping)]
    if not top_positions:
        ax.axis("off")
        ax.text(0.5, 0.5, "暂无可展示的个股信号", ha="center", va="center", fontsize=11.5, color=MUTED)
        return
    symbols = [str(item.get("symbol", "")).upper().strip() for item in top_positions[:4]]
    scores = [(_coerce_float(item.get("score")) or 0.0) for item in top_positions[:4]]
    colors = [BAR_COLORS.get(_normalize(str(item.get("symbol", ""))), "#64748b") for item in top_positions[:4]]
    ax.bar(symbols, scores, color=colors, alpha=0.9)
    ax.axhline(0.0, color="#8fa3b5", linewidth=1.0, linestyle="--")
    ax.set_title("单股信号强度（归一分位）", fontsize=10.2, fontweight="bold", color=INK, loc="left", pad=8)
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylabel("模型信号", color=MUTED, fontsize=8.5)
    ax.text(0.02, 0.02, "曲线缺失时以信号强度替代。", transform=ax.transAxes, ha="left", va="bottom", fontsize=8.0, color=MUTED)


def _to_percentiles(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    ordered = sorted((float(value), index) for index, value in enumerate(values))
    if len(ordered) == 1:
        return [50.0]
    result = [0.0 for _ in values]
    for rank, (_, index) in enumerate(ordered):
        result[index] = (rank / (len(ordered) - 1)) * 100.0
    return result


def _summary_cards(brief: Mapping[str, Any], *, phase: str) -> list[tuple[str, str, str]]:
    strategies = list(brief.get("strategies") or [])
    summary = dict(brief.get("summary") or {})
    if phase == "research":
        agreements = [_agreement_ratio(strategy) for strategy in strategies if isinstance(strategy, Mapping)]
        avg_agreement = mean(agreements) if agreements else 0.0
        top_weight = max((_top_weight(strategy) for strategy in strategies), default=0.0)
        return [
            ("策略数", str(summary.get("strategy_count", len(strategies))), HEADER_ACCENT),
            ("目标仓位", str(summary.get("positive_target_count", 0)), "#457b9d"),
            ("一致性", f"{avg_agreement * 100.0:.0f}%", "#1b998b"),
            ("核心权重", f"{top_weight * 100.0:.1f}%", "#ffb703"),
        ]

    first = dict(strategies[0]) if strategies else {}
    account = dict(first.get("account") or {})
    planning_equity = _coerce_float(account.get("planning_equity"))
    if planning_equity is None:
        planning_equity = _coerce_float(account.get("equity")) or 0.0
    return [
        ("策略数", str(summary.get("strategy_count", len(strategies))), "#1d3557"),
        ("已提单", str(summary.get("submitted_count", 0)), "#457b9d"),
        ("未完成", str(summary.get("open_order_count", 0)), "#e76f51"),
        ("计划权益", f"{planning_equity:,.0f}", "#0b6e4f"),
    ]


def _compact_slice_items(
    items: Sequence[Mapping[str, Any]],
    *,
    label_key: str,
    value_key: str,
    max_items: int,
    other_label: str,
) -> list[tuple[str, float]]:
    pairs: list[tuple[str, float]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get(label_key, "")).strip()
        value = abs(_coerce_float(item.get(value_key)) or 0.0)
        if not label or value <= 0:
            continue
        pairs.append((label, value))
    pairs.sort(key=lambda item: item[1], reverse=True)
    if len(pairs) <= max_items:
        return pairs
    kept = pairs[: max_items - 1]
    other_value = sum(value for _, value in pairs[max_items - 1 :])
    if other_value > 0:
        kept.append((other_label, other_value))
    return kept


def _strategy_label(strategy: Mapping[str, Any]) -> str:
    strategy_id = str(strategy.get("strategy_id") or "").strip()
    fallback = str(strategy.get("strategy_alias") or strategy.get("strategy_name") or strategy_id or "未命名策略")
    return strategy_cn_name(strategy_id, fallback=fallback)


def _display_expert_name(name: str) -> str:
    mapping = {
        "lightgbm": "LightGBM",
        "xgboost": "XGBoost",
        "catboost": "CatBoost",
        "lstm": "LSTM",
        "transformer": "Transformer",
        "ensemble": "Voting",
    }
    return mapping.get(_normalize(name), name)


def _agreement_ratio(strategy: Mapping[str, Any]) -> float:
    snapshot = dict(strategy.get("expert_snapshot") or {})
    return _coerce_float(snapshot.get("agreement_ratio")) or 0.0


def _top_weight(strategy: Mapping[str, Any]) -> float:
    top_positions = list(strategy.get("top_positions") or [])
    values = [max(0.0, _coerce_float(item.get("target_weight")) or 0.0) for item in top_positions if isinstance(item, Mapping)]
    return max(values, default=0.0)


def _chart_leaders_text(strategy: Mapping[str, Any]) -> str:
    top_positions = list(strategy.get("top_positions") or [])
    parts = []
    for item in top_positions[:3]:
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        weight = (_coerce_float(item.get("target_weight")) or 0.0) * 100.0
        parts.append(f"{symbol} {weight:.1f}%")
    return " | ".join(parts) if parts else "暂无重点仓位"


def _parse_iso_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    date_text = text[:10]
    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except Exception:
        return None


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except Exception:
        return _parse_iso_date(text)


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric


def _coerce_int(value: Any) -> int | None:
    numeric = _coerce_float(value)
    if numeric is None:
        return None
    return int(numeric)


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _save_figure(fig: plt.Figure, output_path) -> None:
    fig.savefig(output_path, dpi=240, facecolor=fig.get_facecolor(), bbox_inches=None, pad_inches=0.06)
    plt.close(fig)
