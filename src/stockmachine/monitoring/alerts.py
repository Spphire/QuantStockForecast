from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import json

from stockmachine.monitoring.reports import PaperRunFailure, PaperRunReport


TERMINAL_ORDER_STATUSES = {"filled", "canceled", "cancelled", "rejected", "expired"}


@dataclass(slots=True, frozen=True)
class OperatorAlert:
    code: str
    severity: str
    title: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "details": dict(self.details),
        }


def build_operator_alerts(
    *,
    report: PaperRunReport | Mapping[str, Any] | None = None,
    state_payload: Mapping[str, Any] | None = None,
    reference_date: date | None = None,
    stale_after_days: int = 2,
) -> tuple[OperatorAlert, ...]:
    resolved_reference_date = reference_date or date.today()
    alerts: dict[str, OperatorAlert] = {}
    failures = _report_failures(report)
    state_payload = dict(state_payload or {})

    if _contains_failure(
        failures,
        {
            "data_stale",
            "stale_data",
            "data_freshness",
            "missing_silver_data",
            "no_silver_session_on_or_before_target",
            "previous_available_session_not_allowed",
        },
    ):
        _add_alert(
            alerts,
            OperatorAlert(
                code="data_stale",
                severity="warning",
                title="Market data looks stale",
                message="The run report indicates that the data snapshot is older than expected.",
                details=_failure_details(
                    failures,
                    {
                        "data_stale",
                        "stale_data",
                        "data_freshness",
                        "missing_silver_data",
                        "no_silver_session_on_or_before_target",
                        "previous_available_session_not_allowed",
                    },
                ),
            ),
        )

    state_stale_details = _state_staleness(state_payload, resolved_reference_date, stale_after_days)
    if state_stale_details is not None:
        _add_alert(
            alerts,
            OperatorAlert(
                code="data_stale",
                severity="warning",
                title="Market data looks stale",
                message="The latest run state points to a session outside the freshness window.",
                details=state_stale_details,
            ),
        )

    if _contains_failure(failures, {"duplicate_run_blocked", "duplicate_run", "already_running", "duplicate_completed_run"}):
        _add_alert(
            alerts,
            OperatorAlert(
                code="duplicate_run_blocked",
                severity="warning",
                title="Duplicate run was blocked",
                message="A duplicate paper run was prevented by the runner or its guard rails.",
                details=_failure_details(
                    failures,
                    {"duplicate_run_blocked", "duplicate_run", "already_running", "duplicate_completed_run"},
                ),
            ),
        )

    if _contains_failure(failures, {"broker_rejection", "order_rejected", "rejected_by_broker"}):
        _add_alert(
            alerts,
            OperatorAlert(
                code="broker_rejection",
                severity="critical",
                title="Broker rejected an order",
                message="One or more submitted orders were rejected by the broker.",
                details=_failure_details(failures, {"broker_rejection", "order_rejected", "rejected_by_broker"}),
            ),
        )

    if state_payload:
        open_orders = _load_open_order_statuses(state_payload)
        if open_orders:
            _add_alert(
                alerts,
                OperatorAlert(
                    code="open_orders_lingering",
                    severity="warning",
                    title="Open orders are still lingering",
                    message="The latest run still has non-terminal broker orders.",
                    details={
                        "open_order_count": len(open_orders),
                        "symbols": sorted({str(item.get("symbol", "")) for item in open_orders}),
                        "statuses": sorted({str(item.get("status", "")) for item in open_orders}),
                    },
                ),
            )

        rejected_orders = [
            item
            for item in open_orders
            if str(item.get("status", "")).lower() in {"rejected", "reject"}
        ]
        if rejected_orders:
            _add_alert(
                alerts,
                OperatorAlert(
                    code="broker_rejection",
                    severity="critical",
                    title="Broker rejected an order",
                    message="The latest run state contains rejected broker orders.",
                    details={
                        "rejected_order_count": len(rejected_orders),
                        "symbols": sorted({str(item.get("symbol", "")) for item in rejected_orders}),
                    },
                ),
            )

    return tuple(alerts.values())


def _add_alert(alerts: dict[str, OperatorAlert], alert: OperatorAlert) -> None:
    existing = alerts.get(alert.code)
    if existing is None:
        alerts[alert.code] = alert
        return

    merged_details = dict(existing.details)
    for key, value in alert.details.items():
        if key not in merged_details:
            merged_details[key] = value
    alerts[alert.code] = OperatorAlert(
        code=existing.code,
        severity=_max_severity(existing.severity, alert.severity),
        title=existing.title,
        message=existing.message,
        details=merged_details,
    )


def _max_severity(left: str, right: str) -> str:
    order = {"info": 0, "warning": 1, "critical": 2}
    return left if order.get(left, 0) >= order.get(right, 0) else right


def _report_value(report: PaperRunReport | Mapping[str, Any] | None, key: str, default: Any = None) -> Any:
    if report is None:
        return default
    if isinstance(report, Mapping):
        return report.get(key, default)
    if hasattr(report, key):
        return getattr(report, key)
    return default


def _report_failures(report: PaperRunReport | Mapping[str, Any] | None) -> tuple[PaperRunFailure | Mapping[str, Any], ...]:
    if report is None:
        return ()
    failures = _report_value(report, "failures", ())
    if isinstance(failures, tuple):
        return failures
    if isinstance(failures, list):
        return tuple(failures)
    return tuple(failures or ())


def _contains_failure(failures: Sequence[PaperRunFailure | Mapping[str, Any]], needles: set[str]) -> bool:
    normalized_needles = {needle.lower() for needle in needles}
    for failure in failures:
        stage = str(_item_value(failure, "stage", default="")).lower()
        reason = str(_item_value(failure, "reason", default="")).lower()
        if any(needle in stage or needle in reason for needle in normalized_needles):
            return True
    return False


def _failure_details(
    failures: Sequence[PaperRunFailure | Mapping[str, Any]],
    needles: set[str],
) -> dict[str, Any]:
    matched = []
    normalized_needles = {needle.lower() for needle in needles}
    for failure in failures:
        stage = str(_item_value(failure, "stage", default="")).lower()
        reason = str(_item_value(failure, "reason", default="")).lower()
        if any(needle in stage or needle in reason for needle in normalized_needles):
            matched.append(
                {
                    "stage": _item_value(failure, "stage", default=""),
                    "reason": _item_value(failure, "reason", default=""),
                    "details": _json_safe(_item_value(failure, "details", default={})),
                }
            )
    return {"matched_failures": matched}


def _state_staleness(
    state_payload: Mapping[str, Any],
    reference_date: date,
    stale_after_days: int,
) -> dict[str, Any] | None:
    if not state_payload:
        return None

    if state_payload.get("stale") or state_payload.get("is_stale"):
        return {"reason": "explicit_stale_flag", "state": _json_safe(state_payload)}

    for key in ("rebalance_date", "session_date", "effective_session_date"):
        raw_value = state_payload.get(key)
        if not raw_value:
            continue
        parsed = _coerce_date(raw_value)
        if parsed is None:
            continue
        age_days = (reference_date - parsed).days
        if age_days >= stale_after_days:
            return {
                "reason": "state_date",
                "state_date": parsed.isoformat(),
                "snapshot_age_days": age_days,
                "stale_after_days": stale_after_days,
                "state": _json_safe(state_payload),
            }
    return None


def _load_open_order_statuses(state_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    status_path = str(state_payload.get("submitted_order_statuses_path") or "").strip()
    if not status_path:
        return []

    path = Path(status_path)
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    open_orders: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("status", "")).lower() not in TERMINAL_ORDER_STATUSES:
            open_orders.append(dict(item))
    return open_orders


def _item_value(payload: PaperRunFailure | Mapping[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(payload, Mapping):
        return payload.get(key, default)
    if is_dataclass(payload) and hasattr(payload, key):
        return getattr(payload, key)
    if hasattr(payload, key):
        return getattr(payload, key)
    return default


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if is_dataclass(value):
        return asdict(value)
    return value
