"""Briefing skills and composition helpers for paper-ops reports."""

from execution.managed.briefing.chart_assets import (
    generate_brief_chart_assets,
    render_allocation_pie_chart,
    render_current_distribution_pie_chart,
    render_expert_voting_compare_chart,
    render_pool_curve_chart,
    render_signal_strength_chart,
    render_symbol_curve_chart,
    render_total_pnl_curve_chart,
)
from execution.managed.briefing.html_renderer import (
    render_operation_brief_html_page,
)
from execution.managed.briefing.presenter import (
    compact_action_text,
    format_generated_time_cn,
    strategy_cn_name,
    top_positions_text,
)

__all__ = [
    "generate_brief_chart_assets",
    "compact_action_text",
    "format_generated_time_cn",
    "render_allocation_pie_chart",
    "render_current_distribution_pie_chart",
    "render_expert_voting_compare_chart",
    "render_operation_brief_html_page",
    "render_pool_curve_chart",
    "render_signal_strength_chart",
    "render_symbol_curve_chart",
    "render_total_pnl_curve_chart",
    "strategy_cn_name",
    "top_positions_text",
]
