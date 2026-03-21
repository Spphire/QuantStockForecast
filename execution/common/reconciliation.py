"""Reconcile target positions against current broker positions."""

from __future__ import annotations

from typing import Iterable

from execution.common.execution_models import OrderIntent, PositionSnapshot, TargetPosition


def current_positions_by_symbol(positions: Iterable[PositionSnapshot]) -> dict[str, PositionSnapshot]:
    return {position.symbol: position for position in positions}


def normalize_current_weights(
    positions: list[PositionSnapshot], *, account_equity: float
) -> list[PositionSnapshot]:
    normalized: list[PositionSnapshot] = []
    for position in positions:
        weight = position.market_value / account_equity if account_equity > 0 else 0.0
        normalized.append(
            PositionSnapshot(
                symbol=position.symbol,
                qty=position.qty,
                market_value=position.market_value,
                current_price=position.current_price,
                weight=weight,
                raw=dict(position.raw),
            )
        )
    return normalized


def resolve_submit_mode(side: str, order_sizing_mode: str) -> str:
    mode = str(order_sizing_mode or "notional").lower()
    if mode == "hybrid":
        return "notional" if side == "buy" else "qty"
    if mode not in {"notional", "qty"}:
        raise ValueError(f"Unsupported order_sizing_mode: {order_sizing_mode}")
    return mode


def build_order_intents(
    targets: list[TargetPosition],
    current_positions: list[PositionSnapshot],
    *,
    account_equity: float,
    planning_equity: float,
    allow_fractional: bool,
    order_sizing_mode: str,
    order_type: str,
    time_in_force: str,
) -> list[OrderIntent]:
    current_map = current_positions_by_symbol(current_positions)
    intents: list[OrderIntent] = []

    for target in targets:
        target_notional = max(target.target_weight, 0.0) * planning_equity
        current = current_map.get(target.symbol)
        current_notional = current.market_value if current else 0.0
        current_weight = current.weight if current else 0.0
        delta = target_notional - current_notional
        if abs(delta) <= 1e-9:
            continue
        side = "buy" if delta > 0 else "sell"
        submit_as = resolve_submit_mode(side, order_sizing_mode)
        reference_price = target.reference_price
        if reference_price <= 0 and current is not None and current.current_price > 0:
            reference_price = current.current_price
        estimated_qty = abs(delta) / reference_price if reference_price > 0 else 0.0
        intents.append(
            OrderIntent(
                symbol=target.symbol,
                side=side,
                delta_notional=delta,
                reference_price=max(reference_price, 0.0),
                estimated_qty=estimated_qty,
                submit_notional=abs(delta) if submit_as == "notional" else 0.0,
                submit_qty=estimated_qty if submit_as == "qty" else 0.0,
                target_weight=target.target_weight,
                current_weight=current_weight,
                current_notional=current_notional,
                target_notional=target_notional,
                order_type=order_type,
                time_in_force=time_in_force,
                allow_fractional=allow_fractional,
                submit_as=submit_as,
                reason=f"{target.action} rebalance from {current_weight:.4f} to {target.target_weight:.4f}",
            )
        )
    return intents
