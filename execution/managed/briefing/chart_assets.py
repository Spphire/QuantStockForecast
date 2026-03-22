from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Circle


CHART_FACE = "#fffdf9"
BORDER = "#d7e0ea"
INK = "#102a43"
MUTED = "#52606d"
GRID = "#e8eef5"
PIE_COLORS = ["#0b6e4f", "#1b998b", "#457b9d", "#ffb703", "#e76f51", "#8ecae6", "#adb5bd"]
SERIES_COLORS = ["#1d3557", "#457b9d", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51", "#8ecae6"]
BAR_COLORS = {
    "lightgbm": "#457b9d",
    "xgboost": "#2a9d8f",
    "catboost": "#e76f51",
    "lstm": "#e9c46a",
    "transformer": "#8ecae6",
    "ensemble": "#0b6e4f",
}


def generate_brief_chart_assets(*, brief: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    phase = str(brief.get("phase") or "")
    strategies = [dict(item) for item in list(brief.get("strategies") or [])[:2] if isinstance(item, Mapping)]
    payload: list[dict[str, Any]] = []
    for index, strategy in enumerate(strategies, start=1):
        strategy_id = str(strategy.get("strategy_id") or f"strategy_{index}")
        strategy_dir = output_dir / f"{index:02d}_{_slugify(strategy_id)}"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        if phase == "research":
            charts = _render_research_strategy_charts(strategy=strategy, output_dir=strategy_dir)
        else:
            charts = _render_submit_strategy_charts(strategy=strategy, output_dir=strategy_dir)
        payload.append(
            {
                "strategy_id": strategy_id,
                "strategy_name": str(strategy.get("strategy_alias") or strategy.get("strategy_name") or strategy_id),
                "rebalance_date": str(strategy.get("rebalance_date") or ""),
                "explain_like_human": str(strategy.get("explain_like_human") or ""),
                "strategy_overview": _build_strategy_overview(strategy=strategy, phase=phase),
                "top_positions_text": _top_positions_text(list(strategy.get("top_positions") or []), limit=3),
                "submitted_count": int(_coerce_int(strategy.get("submitted_count")) or 0),
                "open_order_count": int(_coerce_int(strategy.get("open_order_count")) or 0),
                "agreement_ratio": float(_coerce_float((strategy.get("expert_snapshot") or {}).get("agreement_ratio")) or 0.0),
                "research_conclusion": str(strategy.get("research_conclusion") or ""),
                "alerts": [dict(item) for item in list(strategy.get("alerts") or []) if isinstance(item, Mapping)],
                "chart_explanations": _chart_explanations(phase=phase),
                "charts": charts,
            }
        )
    return {"phase": phase, "strategies": payload, "chart_dir": str(output_dir)}


def _render_research_strategy_charts(*, strategy: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    # 固定研究简报图表规范：key、文件名、渲染函数一一对应，避免隐式变化。
    chart_specs = (
        ("allocation_pie", "allocation_pie.png", render_allocation_pie_chart),
        ("pool_curve", "pool_curve.png", render_pool_curve_chart),
        ("expert_compare", "expert_compare.png", render_expert_voting_compare_chart),
    )
    charts: dict[str, str] = {}
    for key, filename, renderer in chart_specs:
        output_path = output_dir / filename
        renderer(strategy=strategy, output_path=output_path)
        charts[key] = str(output_path)
    return charts


def _render_submit_strategy_charts(*, strategy: Mapping[str, Any], output_dir: Path) -> dict[str, str]:
    # 固定执行简报图表规范：key、文件名、渲染函数一一对应，避免隐式变化。
    chart_specs = (
        ("current_distribution_pie", "current_distribution_pie.png", render_current_distribution_pie_chart),
        ("total_pnl_curve", "total_pnl_curve.png", render_total_pnl_curve_chart),
        ("signal_strength", "signal_strength.png", render_signal_strength_chart),
    )
    charts: dict[str, str] = {}
    for key, filename, renderer in chart_specs:
        output_path = output_dir / filename
        renderer(strategy=strategy, output_path=output_path)
        charts[key] = str(output_path)
    # Backward-compatible alias for legacy submit template consumers.
    charts["symbol_curve"] = charts.get("signal_strength", "")
    return charts


def render_allocation_pie_chart(*, strategy: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pool_weights = [dict(item) for item in list(strategy.get("pool_expected_weights") or []) if isinstance(item, Mapping)]
        if pool_weights:
            _render_pool_weight_bar_chart(strategy=strategy, pool_weights=pool_weights, output_path=output_path)
            return
        items = _compact_slice_items(
            list(strategy.get("top_positions") or []),
            label_key="symbol",
            value_key="target_weight",
            max_items=6,
            other_label="其他",
        )
        if not items:
            _render_placeholder(output_path, title="目标仓位分布", message="暂无目标仓位")
            return
        labels, values = zip(*items)
        values_num = [max(0.0, _coerce_float(item) or 0.0) for item in values]
        if sum(values_num) <= 0:
            _render_placeholder(output_path, title="目标仓位分布", message="暂无目标仓位")
            return
        fig, ax = _new_figure()
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
            textprops={"fontsize": 8.5, "color": INK},
        )
        ax.add_artist(Circle((0, 0), 0.47, facecolor=CHART_FACE, edgecolor="none", zorder=0))
        ax.set_title("目标仓位分布", fontsize=11, fontweight="bold", color=INK, loc="left", pad=10)
        ax.text(
            0.0,
            -1.18,
            "说明：仅展示本轮入选仓位；未入选股票目标仓位为 0%。",
            ha="center",
            va="center",
            fontsize=8.2,
            color=MUTED,
            transform=ax.transData,
        )
        ax.set_aspect("equal")
        _save_figure(fig, output_path)
    except Exception as exc:
        _render_placeholder(output_path, title="目标仓位分布", message=f"图表生成失败：{exc}")


def render_current_distribution_pie_chart(*, strategy: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        items = _compact_slice_items(
            list(strategy.get("current_distribution") or []),
            label_key="label",
            value_key="value",
            max_items=7,
            other_label="其他",
        )
        if not items:
            _render_placeholder(output_path, title="当前账户持仓分布（含现金）", message="暂无当前账户持仓")
            return
        labels, values = zip(*items)
        values_num = [max(0.0, _coerce_float(item) or 0.0) for item in values]
        total = sum(values_num)
        if total <= 0:
            _render_placeholder(output_path, title="当前账户持仓分布（含现金）", message="暂无当前账户持仓")
            return
        fig, ax = _new_figure()
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
            textprops={"fontsize": 8.5, "color": INK},
        )
        ax.add_artist(Circle((0, 0), 0.47, facecolor=CHART_FACE, edgecolor="none", zorder=0))
        currency = str((strategy.get("account") or {}).get("currency") or "USD")
        ax.set_title("当前账户持仓分布（含现金）", fontsize=11, fontweight="bold", color=INK, loc="left", pad=10)
        ax.text(0.0, -1.18, f"总金额 {total:,.0f} {currency}", ha="center", va="center", fontsize=8.5, color=MUTED, transform=ax.transData)
        ax.set_aspect("equal")
        _save_figure(fig, output_path)
    except Exception as exc:
        _render_placeholder(output_path, title="当前账户持仓分布（含现金）", message=f"图表生成失败：{exc}")


def render_pool_curve_chart(*, strategy: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        curves = dict(strategy.get("research_curves") or {})
        fig, ax = _new_figure()
        series: list[tuple[str, list[dict[str, Any]], list[datetime | None], bool]] = []
        for symbol, points in curves.items():
            points_list = [dict(item) for item in list(points) if isinstance(item, Mapping)]
            if len(points_list) < 2:
                continue
            parsed_dates = [_parse_iso_date(item.get("date")) for item in points_list]
            has_valid_dates = all(value is not None for value in parsed_dates)
            series.append((str(symbol), points_list, parsed_dates, has_valid_dates))
        if not series:
            plt.close(fig)
            _render_placeholder(output_path, title="股票池曲线", message="暂无股票池曲线")
            return
        use_date_axis = all(has_dates for _, _, _, has_dates in series)
        for index, (symbol, points_list, parsed_dates, _) in enumerate(series):
            xs = parsed_dates if use_date_axis else list(range(len(points_list)))
            ys = [(_coerce_float(item.get("normalized_close")) or 1.0) * 100.0 for item in points_list]
            ax.plot(xs, ys, linewidth=2.0, label=symbol, color=SERIES_COLORS[index % len(SERIES_COLORS)])
        ax.grid(axis="y", color=GRID, linewidth=0.9)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylabel("首日 = 100", fontsize=9, color=MUTED)
        if use_date_axis:
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=6))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
            ax.set_xlabel("日期（MM-DD）", fontsize=8.5, color=MUTED)
            ax.tick_params(axis="x", labelsize=7.8)
        else:
            ax.set_xlabel("样本序号（按日期先后）", fontsize=8.5, color=MUTED)
        ax.set_title("股票池曲线", fontsize=11, fontweight="bold", color=INK, loc="left", pad=9)
        ax.legend(loc="upper left", fontsize=7.2, frameon=False, ncol=2)
        curve_window = int(_coerce_int(strategy.get("research_curve_lookback")) or 0)
        input_window = int(_coerce_int(strategy.get("expert_input_window")) or 0)
        curve_rule = str(strategy.get("research_curve_rule") or "")
        note_parts = []
        if use_date_axis:
            note_parts.append("说明：横轴为交易日期（MM-DD）；纵轴统一到首日=100，用于比较相对涨跌，不表示绝对股价。")
        else:
            note_parts.append("说明：横轴为样本序号（按日期先后）；纵轴统一到首日=100，用于比较相对涨跌，不表示绝对股价。")
        if curve_window > 0 and input_window > 0:
            note_parts.append(
                f"当前展示约 {curve_window} 个交易日；规则：{curve_rule or 'expert_input_x2'}（expert 输入窗口约 {input_window} 日）。"
            )
        ax.text(
            0.02,
            0.02,
            "\n".join(note_parts),
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.0,
            color=INK,
            bbox={"boxstyle": "round,pad=0.26", "facecolor": "#f8fafc", "edgecolor": BORDER},
        )
        _save_figure(fig, output_path)
    except Exception as exc:
        _render_placeholder(output_path, title="股票池曲线", message=f"图表生成失败：{exc}")


def render_expert_voting_compare_chart(*, strategy: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        snapshot = dict(strategy.get("expert_snapshot") or {})
        symbols = [str(item).upper().strip() for item in list(snapshot.get("symbols") or []) if str(item).strip()]
        experts = [str(item).strip() for item in list(snapshot.get("experts") or []) if str(item).strip()]
        score_map = snapshot.get("scores")
        if not symbols or not experts or not isinstance(score_map, Mapping):
            _render_placeholder(output_path, title="Expert 与 Voting 对比", message="暂无 expert / voting 快照")
            return
        fig, ax = _new_figure()
        width = max(0.10, 0.78 / max(1, len(experts)))
        x_base = list(range(len(symbols)))
        has_value = False
        for index, expert in enumerate(experts):
            expert_values = score_map.get(expert) if isinstance(score_map.get(expert), Mapping) else {}
            raw_values = []
            for symbol in symbols:
                value = _coerce_float(expert_values.get(symbol))
                if value is None:
                    value = 0.0
                else:
                    has_value = True
                raw_values.append(value)
            values = _to_percentiles(raw_values)
            offset = (index - (len(experts) - 1) / 2.0) * width
            xs = [item + offset for item in x_base]
            color = BAR_COLORS.get(_normalize(expert), "#64748b")
            ax.bar(xs, values, width=width * 0.9, label=_display_expert_name(expert), color=color, alpha=0.92 if _normalize(expert) == "ensemble" else 0.82)
        if not has_value:
            plt.close(fig)
            _render_placeholder(output_path, title="Expert 与 Voting 对比", message="专家预测为空")
            return
        ax.axhline(50.0, color="#8fa3b5", linewidth=1.0, linestyle="--")
        ax.set_xticks(x_base)
        ax.set_xticklabels(symbols, fontsize=8)
        ax.grid(axis="y", color=GRID, linewidth=0.9)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylim(0.0, 100.0)
        ax.set_ylabel("池内相对分位（0-100，越高越偏好）", fontsize=9, color=MUTED)
        ax.set_title("Expert 与 Voting 对比（已归一到相对分位）", fontsize=11, fontweight="bold", color=INK, loc="left", pad=9)
        ax.legend(loc="upper left", fontsize=7.1, frameon=False, ncol=3)
        ax.text(
            0.02,
            0.02,
            "说明：不同专家原始量纲不可直接比；这里统一归一为池内相对分位（0-100），越高代表该专家相对更偏好。",
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.0,
            color=MUTED,
            bbox={"boxstyle": "round,pad=0.24", "facecolor": "#f8fafc", "edgecolor": BORDER},
        )
        _save_figure(fig, output_path)
    except Exception as exc:
        _render_placeholder(output_path, title="Expert 与 Voting 对比", message=f"图表生成失败：{exc}")


def render_total_pnl_curve_chart(*, strategy: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        curve = [dict(item) for item in list(strategy.get("equity_curve") or []) if isinstance(item, Mapping)]
        if not curve:
            _render_placeholder(output_path, title="账户权益曲线（现金+持仓）", message="账户权益曲线样本不足")
            return
        fig, ax = _new_figure()
        parsed_times = [
            _parse_iso_datetime(item.get("timestamp_utc")) or _parse_iso_date(item.get("date"))
            for item in curve
        ]
        use_date_axis = all(value is not None for value in parsed_times)
        xs = parsed_times if use_date_axis else list(range(len(curve)))
        equity_values = [_coerce_float(item.get("equity")) for item in curve]
        has_equity_values = all(value is not None for value in equity_values)
        if has_equity_values and equity_values:
            ys = [float(item or 0.0) for item in equity_values]
            ax.plot(xs, ys, color="#1d3557", linewidth=2.1, marker="o", markersize=3.0)
            base = ys[0] if ys else 0.0
            ax.fill_between(xs, ys, base, color="#a8dadc", alpha=0.22)
            currency = str((strategy.get("account") or {}).get("currency") or "USD")
            ax.set_ylabel(f"账户权益 ({currency})", fontsize=9, color=MUTED)
        else:
            ys = [(_coerce_float(item.get("pnl_pct")) or 0.0) * 100.0 for item in curve]
            ax.plot(xs, ys, color="#1d3557", linewidth=2.1, marker="o", markersize=3.0)
            ax.fill_between(xs, ys, 0.0, color="#a8dadc", alpha=0.28)
            ax.axhline(0.0, color="#8fa3b5", linewidth=1.0, linestyle="--")
            ax.set_ylabel("累计收益 (%)", fontsize=9, color=MUTED)
        if use_date_axis:
            day_values = {value.date() for value in parsed_times if value is not None}
            if len(curve) == 1:
                x0 = parsed_times[0]
                ax.set_xlim(x0 - timedelta(hours=12), x0 + timedelta(hours=12))
                ax.set_xticks([x0])
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
                ax.set_xlabel("日期", fontsize=8.5, color=MUTED)
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
                    ax.set_xlabel("日期", fontsize=8.5, color=MUTED)
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
                    ax.set_xlabel("时间", fontsize=8.5, color=MUTED)
            ax.tick_params(axis="x", labelsize=7.8)
        else:
            ax.set_xlabel("样本序号（按时间先后）", fontsize=8.5, color=MUTED)
        ax.grid(axis="y", color=GRID, linewidth=0.9)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_title("账户权益曲线（现金+持仓）", fontsize=11, fontweight="bold", color=INK, loc="left", pad=9)
        if len(curve) == 1:
            ax.text(
                0.02,
                0.96,
                "当前仅 1 个样本点，曲线稳定性有限。",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=8.0,
                color=MUTED,
                bbox={"boxstyle": "round,pad=0.24", "facecolor": "#f8fafc", "edgecolor": BORDER},
            )
        _save_figure(fig, output_path)
    except Exception as exc:
        _render_placeholder(output_path, title="账户权益曲线（现金+持仓）", message=f"图表生成失败：{exc}")


def render_signal_strength_chart(*, strategy: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig, ax = _new_figure()
        top_positions = [dict(item) for item in list(strategy.get("top_positions") or []) if isinstance(item, Mapping)]
        ranked = sorted(
            top_positions,
            key=lambda item: _coerce_float(item.get("target_weight")) or 0.0,
            reverse=True,
        )
        ranked = [item for item in ranked if str(item.get("symbol") or "").strip()][:6]
        if not ranked:
            plt.close(fig)
            _render_placeholder(output_path, title="单股信号强度（归一分位）", message="暂无可展示的个股信号")
            return

        symbols = [str(item.get("symbol") or "").upper().strip() for item in ranked]
        raw_scores = [_coerce_float(item.get("score")) for item in ranked]
        if all(value is None for value in raw_scores):
            plt.close(fig)
            _render_placeholder(output_path, title="单股信号强度（归一分位）", message="暂无可用信号分数")
            return

        score_values = [float(value or 0.0) for value in raw_scores]
        percentiles = _to_percentiles(score_values)
        bars = ax.bar(symbols, percentiles, color=SERIES_COLORS[: len(symbols)], alpha=0.9, label="信号分位")
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
        ax.grid(axis="y", color=GRID, linewidth=0.9)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylim(0.0, 100.0)
        ax.set_ylabel("相对分位 (0-100)", fontsize=9, color=MUTED)
        ax.set_title("单股信号强度（归一分位）", fontsize=11, fontweight="bold", color=INK, loc="left", pad=9)
        note = "说明：柱为入选个股 score 的相对分位；折线为 confidence（若有）。" if has_confidence else "说明：柱为入选个股 score 的相对分位（0-100）。"
        ax.text(
            0.02,
            0.02,
            note,
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.0,
            color=MUTED,
            bbox={"boxstyle": "round,pad=0.24", "facecolor": "#f8fafc", "edgecolor": BORDER},
        )
        if has_confidence:
            ax.legend(loc="upper left", fontsize=7.2, frameon=False)
        _save_figure(fig, output_path)
    except Exception as exc:
        _render_placeholder(output_path, title="单股信号强度（归一分位）", message=f"图表生成失败：{exc}")


def render_symbol_curve_chart(*, strategy: Mapping[str, Any], output_path: Path) -> None:
    # Legacy alias kept for callers importing the old name.
    render_signal_strength_chart(strategy=strategy, output_path=output_path)


def _render_symbol_proxy(*, output_path: Path, strategy: Mapping[str, Any]) -> None:
    top_positions = [dict(item) for item in list(strategy.get("top_positions") or []) if isinstance(item, Mapping)]
    if not top_positions:
        _render_placeholder(output_path, title="单股信号强度（归一分位）", message="暂无可展示的个股信号")
        return
    fig, ax = _new_figure()
    symbols = [str(item.get("symbol", "")).upper() for item in top_positions[:4]]
    scores = [(_coerce_float(item.get("score")) or 0.0) for item in top_positions[:4]]
    colors = [BAR_COLORS.get(_normalize(symbol), "#64748b") for symbol in symbols]
    ax.bar(symbols, scores, color=colors, alpha=0.9)
    ax.axhline(0.0, color="#8fa3b5", linewidth=1.0, linestyle="--")
    ax.grid(axis="y", color=GRID, linewidth=0.9)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylabel("模型信号", fontsize=9, color=MUTED)
    ax.set_title("单股信号强弱（曲线缺失替代）", fontsize=11, fontweight="bold", color=INK, loc="left", pad=9)
    _save_figure(fig, output_path)


def _new_figure(figsize: tuple[float, float] = (5.8, 3.6)):
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(CHART_FACE)
    ax.set_facecolor(CHART_FACE)
    for spine in ax.spines.values():
        spine.set_color(BORDER)
        spine.set_linewidth(0.9)
    ax.tick_params(colors=MUTED, labelsize=8)
    return fig, ax


def _render_pool_weight_bar_chart(*, strategy: Mapping[str, Any], pool_weights: Sequence[Mapping[str, Any]], output_path: Path) -> None:
    ranked = [
        {
            "symbol": str(item.get("symbol", "")).upper().strip(),
            "target_weight": max(0.0, _coerce_float(item.get("target_weight")) or 0.0),
        }
        for item in pool_weights
        if isinstance(item, Mapping)
    ]
    ranked = [item for item in ranked if item["symbol"]]
    if not ranked:
        _render_placeholder(output_path, title="股票池期望仓位", message="股票池为空")
        return
    fig, ax = _new_figure(figsize=(6.0, 3.8))
    labels = [item["symbol"] for item in ranked]
    values = [item["target_weight"] * 100.0 for item in ranked]
    colors = ["#0b6e4f" if value > 1e-9 else "#c7d3df" for value in values]
    ax.bar(labels, values, color=colors, alpha=0.92)
    max_value = max(values) if values else 0.0
    y_top = max(8.0, max_value * 1.35)
    ax.set_ylim(0.0, y_top)
    for idx, value in enumerate(values):
        if value <= 1e-9:
            continue
        ax.text(idx, value + y_top * 0.03, f"{value:.1f}%", ha="center", va="bottom", fontsize=7.8, color=INK)
    ax.grid(axis="y", color=GRID, linewidth=0.9)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_ylabel("目标仓位 (%)", fontsize=8.8, color=MUTED)
    ax.set_title("股票池期望仓位分布", fontsize=11, fontweight="bold", color=INK, loc="left", pad=9)
    ax.tick_params(axis="x", labelsize=7.6, rotation=0)
    positive_count = sum(1 for value in values if value > 1e-9)
    source = str(strategy.get("analysis_pool_source") or "config")
    ax.text(
        0.02,
        0.02,
        f"说明：展示股票池内每只股票目标仓位，0%表示本轮未入选。入选 {positive_count}/{len(values)}，池来源：{source}。",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.9,
        color=MUTED,
        bbox={"boxstyle": "round,pad=0.24", "facecolor": "#f8fafc", "edgecolor": BORDER},
    )
    _save_figure(fig, output_path)


def _save_figure(fig: Any, output_path: Path) -> None:
    fig.savefig(output_path, dpi=220, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def _render_placeholder(path: Path, *, title: str, message: str) -> None:
    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    fig.patch.set_facecolor(CHART_FACE)
    ax.set_facecolor(CHART_FACE)
    for spine in ax.spines.values():
        spine.set_color(BORDER)
        spine.set_linewidth(1.0)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(0.5, 0.62, title, ha="center", va="center", fontsize=12, fontweight="bold", color=INK, transform=ax.transAxes)
    ax.text(0.5, 0.44, message, ha="center", va="center", fontsize=9, color=MUTED, transform=ax.transAxes, wrap=True)
    fig.savefig(path, dpi=220, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


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


def _top_positions_text(top_positions: Sequence[Mapping[str, Any]], *, limit: int = 3) -> str:
    parts = []
    for item in list(top_positions or [])[:limit]:
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        weight = (_coerce_float(item.get("target_weight")) or 0.0) * 100.0
        parts.append(f"{symbol} {weight:.1f}%")
    return " / ".join(parts) if parts else "暂无重点仓位"


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


def _slugify(value: str) -> str:
    text = _normalize(value)
    cleaned = []
    for char in text:
        if char.isalnum():
            cleaned.append(char)
        elif char in {"_", "-"}:
            cleaned.append("-")
    result = "".join(cleaned).strip("-")
    return result or "strategy"


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


def _to_percentiles(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    ordered = sorted((value, index) for index, value in enumerate(values))
    if len(ordered) == 1:
        return [50.0]
    result = [0.0 for _ in values]
    for rank, (_, index) in enumerate(ordered):
        result[index] = (rank / (len(ordered) - 1)) * 100.0
    return result


def _build_strategy_overview(*, strategy: Mapping[str, Any], phase: str) -> str:
    explain = str(strategy.get("explain_like_human") or "").strip()
    if phase == "research":
        conclusion = str(strategy.get("research_conclusion") or "").strip()
        if conclusion and explain:
            return f"{conclusion} {explain}"
        return conclusion or explain or "本轮策略暂无明显变化。"
    alerts = [dict(item) for item in list(strategy.get("alerts") or []) if isinstance(item, Mapping)]
    alert_text = "；".join(str(item.get("title") or item.get("code") or "") for item in alerts[:2]) if alerts else "当前无告警"
    if explain:
        return f"{explain} {alert_text}。"
    return f"当前执行状态：{alert_text}。"


def _chart_explanations(*, phase: str) -> dict[str, str]:
    if phase == "research":
        return {
            "allocation_pie": "展示股票池内每只股票的目标仓位，0% 表示本轮未入选。",
            "pool_curve": "横轴为交易日期（MM-DD），纵轴统一到首日=100，用于比较相对涨跌趋势。",
            "expert_compare": "不同专家原始量纲不可直接比，已归一为池内相对分位（0-100）。实际选股还会叠加置信度和风控约束，不是只看单个专家最高分。",
        }
    return {
        "current_distribution_pie": "展示当前账户持仓分布（含现金），用于识别资金集中度。",
        "total_pnl_curve": "仅展示账户权益曲线（现金+持仓），观察账户整体变化轨迹。",
        "signal_strength": "展示重点个股信号强度的归一分位（0-100）；若存在置信度则同步显示。",
    }


__all__ = [
    "generate_brief_chart_assets",
    "render_allocation_pie_chart",
    "render_pool_curve_chart",
    "render_expert_voting_compare_chart",
    "render_current_distribution_pie_chart",
    "render_total_pnl_curve_chart",
    "render_signal_strength_chart",
    "render_symbol_curve_chart",
]
