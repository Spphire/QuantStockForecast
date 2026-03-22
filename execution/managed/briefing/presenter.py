from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


CN_TIMEZONE = timezone(timedelta(hours=8))


def strategy_cn_name(strategy_id: str, *, fallback: str = "") -> str:
    normalized = str(strategy_id or "").strip().lower()
    if "zeroshot" in normalized and "a_share" in normalized and "multi_expert" in normalized:
        return "A股训练零样本多专家策略"
    if "us_full" in normalized and "multi_expert" in normalized:
        return "美股全量训练多专家策略"
    if "zeroshot" in normalized and "a_share" in normalized:
        return "A股训练零样本策略"
    if "us_full" in normalized:
        return "美股全量训练策略"
    if fallback:
        return str(fallback)
    return str(strategy_id or "未命名策略")


def format_generated_time_cn(generated_at_utc: str) -> str:
    raw = str(generated_at_utc or "").strip()
    if not raw:
        return ""
    candidate = raw.replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(candidate)
    except ValueError:
        return raw
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(CN_TIMEZONE)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def top_positions_text(top_positions: Sequence[Mapping[str, Any]], *, limit: int = 3) -> str:
    parts: list[str] = []
    for item in list(top_positions or [])[:limit]:
        symbol = str(item.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        weight = _coerce_float(item.get("target_weight")) or 0.0
        parts.append(f"{symbol} {weight * 100:.1f}%")
    return " / ".join(parts) if parts else "暂无"


def compact_action_text(strategy: Mapping[str, Any]) -> str:
    exits = [str(item).upper().strip() for item in list(strategy.get("exit_symbols") or []) if str(item).strip()]
    exit_text = f"退出 {', '.join(exits[:3])}" if exits else "无退出标的"
    submitted = int(strategy.get("submitted_count", 0) or 0)
    open_orders = int(strategy.get("open_order_count", 0) or 0)
    return f"{exit_text}；已提订单 {submitted} 笔，待成交 {open_orders} 笔"


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
