"""White-box safety checks before sending execution orders."""

from __future__ import annotations

from execution.common.execution_models import ExecutionPlan, OrderIntent, TargetPosition


def ensure_long_only(target_positions: list[TargetPosition]) -> None:
    for target in target_positions:
        if target.target_weight < -1e-9:
            raise ValueError(f"Negative target weight is not allowed for long-only mode: {target.symbol}")


def ensure_weight_budget(target_positions: list[TargetPosition], *, max_total_weight: float = 1.02) -> None:
    total = sum(max(target.target_weight, 0.0) for target in target_positions)
    if total > max_total_weight:
        raise ValueError(f"Target weights exceed budget: {total:.4f} > {max_total_weight:.4f}")


def ensure_max_position_weight(
    target_positions: list[TargetPosition], *, max_position_weight: float
) -> None:
    if max_position_weight <= 0:
        return
    for target in target_positions:
        if target.target_weight > max_position_weight + 1e-9:
            raise ValueError(
                f"Target weight exceeds strategy cap for {target.symbol}: "
                f"{target.target_weight:.4f} > {max_position_weight:.4f}"
            )


def filter_small_orders(
    orders: list[OrderIntent], *, min_order_notional: float
) -> tuple[list[OrderIntent], list[str]]:
    if min_order_notional <= 0:
        return orders, []

    kept: list[OrderIntent] = []
    dropped: list[str] = []
    for order in orders:
        if abs(order.delta_notional) < min_order_notional:
            dropped.append(
                f"Skip {order.symbol} because |delta_notional|={abs(order.delta_notional):.2f} "
                f"is below min_order_notional={min_order_notional:.2f}."
            )
            continue
        kept.append(order)
    return kept, dropped


def validate_execution_plan(
    plan: ExecutionPlan,
    *,
    max_position_weight: float,
    min_order_notional: float,
) -> ExecutionPlan:
    ensure_long_only(plan.target_positions)
    ensure_weight_budget(plan.target_positions)
    ensure_max_position_weight(plan.target_positions, max_position_weight=max_position_weight)
    filtered_orders, dropped_notes = filter_small_orders(
        plan.order_intents,
        min_order_notional=min_order_notional,
    )
    plan.order_intents = filtered_orders
    plan.notes.extend(dropped_notes)
    return plan
