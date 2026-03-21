"""Translate execution plans into Alpaca order submissions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from execution.alpaca.asset_guard import validate_asset_for_order
from execution.alpaca.client import AlpacaBroker
from execution.common.execution_models import ExecutionPlan, OrderIntent, SubmittedOrder


def client_order_id(strategy_id: str, symbol: str, side: str, *, attempt: int) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    compact_strategy = strategy_id.replace("_", "")[:16]
    return f"{compact_strategy}-{symbol}-{side}-{timestamp}-a{attempt}".lower()


def extract_error_message(error: Exception) -> str:
    response = getattr(error, "response", None)
    if response is not None:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        message = str(payload.get("message", "")).strip()
        if message:
            return message
        text = str(getattr(response, "text", "")).strip()
        if text:
            return text
    return str(error).strip() or error.__class__.__name__


def shrink_order_for_retry(order: OrderIntent, shrink_ratio: float) -> OrderIntent:
    ratio = min(max(shrink_ratio, 0.0), 0.999999)
    return replace(
        order,
        delta_notional=order.delta_notional * ratio,
        estimated_qty=order.estimated_qty * ratio,
        submit_notional=order.submit_notional * ratio,
        submit_qty=order.submit_qty * ratio,
        reason=f"{order.reason}; retry_shrunk={ratio:.4f}",
    )


def is_retryable_buy_failure(message: str) -> bool:
    normalized = str(message or "").lower()
    retryable_keywords = [
        "buying power",
        "insufficient",
        "not enough",
        "exceed",
        "available cash",
        "available buying power",
    ]
    return any(keyword in normalized for keyword in retryable_keywords)


def can_retry_buy(order: OrderIntent, attempt: int, max_buy_retries: int, *, retryable: bool) -> bool:
    return order.side == "buy" and retryable and attempt <= max_buy_retries


def build_attempt_log(
    order: OrderIntent,
    *,
    attempt: int,
    client_order_id_value: str,
    submitted: bool,
    status: str,
    order_id: str = "",
    error_message: str = "",
    note: str = "",
) -> dict[str, Any]:
    return {
        "symbol": order.symbol,
        "side": order.side,
        "attempt": attempt,
        "client_order_id": client_order_id_value,
        "submit_as": order.submit_as,
        "requested_notional": order.submit_notional,
        "requested_qty": order.submit_qty,
        "estimated_qty": order.estimated_qty,
        "delta_notional": order.delta_notional,
        "reference_price": order.reference_price,
        "submitted": submitted,
        "status": status,
        "order_id": order_id,
        "error_message": error_message,
        "note": note,
    }


def submit_execution_plan(
    broker: AlpacaBroker,
    plan: ExecutionPlan,
    *,
    cancel_open_orders_first: bool = True,
    buy_retry_shrink_ratio: float = 0.97,
    max_buy_retries: int = 1,
    refresh_status_after_submit: bool = True,
) -> dict[str, list[Any]]:
    if cancel_open_orders_first:
        broker.cancel_open_orders()

    submitted: list[SubmittedOrder] = []
    attempt_logs: list[dict[str, Any]] = []
    order_statuses: list[dict[str, Any]] = []
    for order in plan.order_intents:
        current_order = order
        for attempt in range(1, max_buy_retries + 2):
            current_client_order_id = client_order_id(
                plan.strategy_id,
                current_order.symbol,
                current_order.side,
                attempt=attempt,
            )
            try:
                validate_asset_for_order(broker, current_order)
                submitted_order = broker.submit_order(
                    current_order,
                    client_order_id=current_client_order_id,
                )
                submitted_order.attempt = attempt
                submitted_order.note = current_order.reason
                submitted_order.submit_as = current_order.submit_as
                submitted_order.requested_notional = current_order.submit_notional
                submitted_order.requested_qty = current_order.submit_qty

                immediate_status = submitted_order.status
                if refresh_status_after_submit and submitted_order.order_id:
                    status_payload = broker.get_order(submitted_order.order_id)
                    immediate_status = str(status_payload.get("status", submitted_order.status))
                    order_statuses.append(status_payload)
                submitted_order.status = immediate_status
                submitted.append(submitted_order)
                attempt_logs.append(
                    build_attempt_log(
                        current_order,
                        attempt=attempt,
                        client_order_id_value=current_client_order_id,
                        submitted=True,
                        status=immediate_status,
                        order_id=submitted_order.order_id,
                        note=current_order.reason,
                    )
                )

                rejection_hint = str(
                    status_payload.get("reject_reason", "")
                    if refresh_status_after_submit and submitted_order.order_id
                    else submitted_order.raw.get("reject_reason", "")
                )
                retryable_rejection = is_retryable_buy_failure(rejection_hint)
                if immediate_status.lower() != "rejected" or not can_retry_buy(
                    current_order,
                    attempt,
                    max_buy_retries,
                    retryable=retryable_rejection,
                ):
                    break

                current_order = shrink_order_for_retry(current_order, buy_retry_shrink_ratio)
            except Exception as error:
                error_message = extract_error_message(error)
                attempt_logs.append(
                    build_attempt_log(
                        current_order,
                        attempt=attempt,
                        client_order_id_value=current_client_order_id,
                        submitted=False,
                        status="submit_error",
                        error_message=error_message,
                        note=current_order.reason,
                    )
                )
                if not can_retry_buy(
                    current_order,
                    attempt,
                    max_buy_retries,
                    retryable=is_retryable_buy_failure(error_message),
                ):
                    break
                current_order = shrink_order_for_retry(current_order, buy_retry_shrink_ratio)

    return {
        "submitted_orders": submitted,
        "attempt_logs": attempt_logs,
        "order_statuses": order_statuses,
    }
