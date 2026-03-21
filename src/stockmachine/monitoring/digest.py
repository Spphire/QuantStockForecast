from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import json

from stockmachine.monitoring.alerts import OperatorAlert, build_operator_alerts
from stockmachine.monitoring.healthcheck import build_paper_daily_healthcheck
from stockmachine.monitoring.reports import PaperRunFailure, build_paper_run_report


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE_ROOT = PROJECT_ROOT / "execution" / "state"


def build_run_index_payload(
    *,
    state_root: str | Path | None = None,
    limit: int = 10,
    reference_date: date | None = None,
) -> dict[str, Any]:
    state_root_path = Path(state_root) if state_root is not None else DEFAULT_STATE_ROOT
    entries = [
        _summarize_run(state_dir, reference_date=reference_date)
        for state_dir in _discover_state_dirs(state_root_path)
    ]
    entries = entries[: max(0, int(limit))]
    return {
        "command": "run-index",
        "generated_at_utc": datetime.utcnow().isoformat(),
        "limit": int(limit),
        "count": len(entries),
        "entries": entries,
    }


def build_daily_summary_payload(
    *,
    state_root: str | Path | None = None,
    session_date: date | None = None,
    reference_date: date | None = None,
) -> dict[str, Any]:
    state_root_path = Path(state_root) if state_root is not None else DEFAULT_STATE_ROOT
    run_entries = [
        _summarize_run(state_dir, reference_date=reference_date)
        for state_dir in _discover_state_dirs(state_root_path)
    ]
    target_session_date = session_date or _latest_session_date(run_entries) or date.today()
    runs = [entry for entry in run_entries if entry.get("session_date") == target_session_date.isoformat()]
    alerts = _merge_alerts([entry["alerts"] for entry in runs])
    status_counts = _status_counts(entry.get("status") for entry in runs)

    return {
        "command": "daily-summary",
        "generated_at_utc": datetime.utcnow().isoformat(),
        "session_date": target_session_date.isoformat(),
        "run_count": len(runs),
        "run_ids": [entry["run_id"] for entry in runs],
        "strategy_names": sorted({entry["strategy_name"] for entry in runs if entry.get("strategy_name")}),
        "status_counts": status_counts,
        "order_count": sum(int(entry.get("order_count", 0)) for entry in runs),
        "open_order_count": sum(int(entry.get("open_order_count", 0)) for entry in runs),
        "fill_count": sum(int(entry.get("fill_count", 0)) for entry in runs),
        "rejected_order_count": sum(int(entry.get("rejected_order_count", 0)) for entry in runs),
        "alerts": [alert.to_dict() for alert in alerts],
        "runs": runs,
    }


def build_operator_digest_payload(
    *,
    state_root: str | Path | None = None,
    session_date: date | None = None,
    limit: int = 10,
    reference_date: date | None = None,
) -> dict[str, Any]:
    state_root_path = Path(state_root) if state_root is not None else DEFAULT_STATE_ROOT
    run_index = build_run_index_payload(state_root=state_root_path, limit=limit, reference_date=reference_date)
    daily_summary = build_daily_summary_payload(
        state_root=state_root_path,
        session_date=session_date,
        reference_date=reference_date,
    )
    healthcheck = None
    if daily_summary["runs"]:
        healthcheck = build_paper_daily_healthcheck(
            daily_summary["runs"][0]["strategy_id"],
            state_root=state_root_path,
            reference_date=reference_date,
        )
    alerts = _merge_alerts([entry["alerts"] for entry in run_index["entries"]] + [daily_summary["alerts"]])
    if healthcheck is not None:
        alerts = _merge_alerts([alerts, build_operator_alerts(state_payload=healthcheck.latest_state)])
    return {
        "command": "operator-digest",
        "generated_at_utc": datetime.utcnow().isoformat(),
        "run_index": run_index,
        "daily_summary": daily_summary,
        "healthcheck": healthcheck.to_dict() if healthcheck is not None else None,
        "alerts": [alert.to_dict() for alert in alerts],
    }


def _summarize_run(state_dir: Path, *, reference_date: date | None = None) -> dict[str, Any]:
    latest_state = _load_latest_state(state_dir)
    if latest_state is None:
        missing_report = build_paper_run_report(
            session_date=date.today(),
            dry_run=True,
            stage="ledger_summary",
            counts={"orders": 0, "open_orders": 0, "fill_count": 0},
            failures=(PaperRunFailure(stage="run_status", reason="missing_latest_state"),),
            meta={"source": "monitoring.digest"},
        )
        alert = OperatorAlert(
            code="missing_latest_state",
            severity="warning",
            title="Latest state is missing",
            message="No latest_state.json file was found for this strategy.",
            details={"state_dir": str(state_dir)},
        )
        return {
            "run_id": None,
            "strategy_id": state_dir.name,
            "session_date": None,
            "strategy_name": state_dir.name,
            "status": "missing",
            "order_count": 0,
            "open_order_count": 0,
            "fill_count": 0,
            "rejected_order_count": 0,
            "manifest": {},
            "run": None,
            "report": missing_report.to_dict(),
            "alert_codes": [alert.code],
            "alerts": [alert.to_dict()],
            "open_orders": [],
        }

    strategy_id = str(latest_state.get("strategy_id") or state_dir.name)
    session_date = (
        str(
            latest_state.get("rebalance_date")
            or latest_state.get("session_date")
            or latest_state.get("effective_session_date")
            or ""
        )
        or None
    )
    order_statuses = _load_statuses(latest_state.get("submitted_order_statuses_path"))
    order_count = int(latest_state.get("order_count", latest_state.get("submitted_count", len(order_statuses))) or 0)
    open_orders = [item for item in order_statuses if str(item.get("status", "")).lower() not in {"filled", "canceled", "cancelled", "rejected", "expired"}]
    rejected_orders = [item for item in order_statuses if str(item.get("status", "")).lower() in {"rejected", "reject"}]
    fill_count = len([item for item in order_statuses if str(item.get("status", "")).lower() == "filled"])
    report = build_paper_run_report(
        session_date=_parse_date(session_date) or date.today(),
        dry_run=bool(latest_state.get("dry_run", not bool(latest_state.get("submit_mode", False)))),
        stage=str(latest_state.get("stage", "ledger_summary")),
        counts={"orders": order_count, "open_orders": len(open_orders), "fill_count": fill_count},
        failures=(
            (
                PaperRunFailure(
                    stage="broker_reconciliation",
                    reason="broker_rejection",
                    details={"rejected_order_count": len(rejected_orders)},
                ),
            )
            if rejected_orders
            else ()
        ),
        meta={"source": "monitoring.digest", "latest_state": _json_safe(latest_state)},
        run_id=str(latest_state.get("run_id") or ""),
        status=str(latest_state.get("status") or ("failed" if rejected_orders else "success")),
    )
    alerts = build_operator_alerts(report=report, state_payload=latest_state, reference_date=reference_date)
    return {
        "run_id": str(latest_state.get("run_id") or ""),
        "strategy_id": strategy_id,
        "session_date": session_date,
        "strategy_name": str(latest_state.get("strategy_name") or strategy_id),
        "generated_at_utc": str(latest_state.get("generated_at_utc") or latest_state.get("run_started_at_utc") or ""),
        "dry_run": bool(latest_state.get("dry_run", not bool(latest_state.get("submit_mode", False)))),
        "status": report.status,
        "order_count": order_count,
        "open_order_count": len(open_orders),
        "fill_count": fill_count,
        "rejected_order_count": len(rejected_orders),
        "manifest": _json_safe(latest_state.get("manifest", {})),
        "run": _json_safe(latest_state),
        "report": report.to_dict(),
        "alert_codes": [alert.code for alert in alerts],
        "alerts": [alert.to_dict() for alert in alerts],
        "open_orders": [dict(item) for item in open_orders],
    }


def _discover_state_dirs(state_root: Path) -> list[Path]:
    if not state_root.exists():
        return []
    return sorted(
        [path for path in state_root.iterdir() if path.is_dir()],
        key=lambda path: _state_mtime(path),
        reverse=True,
    )


def _state_mtime(state_dir: Path) -> float:
    latest_state = state_dir / "latest_state.json"
    if latest_state.exists():
        return latest_state.stat().st_mtime
    order_journal = state_dir / "order_journal.csv"
    if order_journal.exists():
        return order_journal.stat().st_mtime
    return state_dir.stat().st_mtime


def _load_latest_state(state_dir: Path) -> dict[str, Any] | None:
    latest_state_path = state_dir / "latest_state.json"
    if not latest_state_path.exists():
        return None
    try:
        payload = json.loads(latest_state_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, Mapping):
        return None
    return dict(payload)


def _load_statuses(path_value: Any) -> list[dict[str, Any]]:
    if not path_value:
        return []
    path = Path(str(path_value))
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, Mapping)]


def _latest_session_date(entries: Sequence[Mapping[str, Any]]) -> date | None:
    session_dates = [_parse_date(entry.get("session_date")) for entry in entries]
    session_dates = [session_date for session_date in session_dates if session_date is not None]
    if not session_dates:
        return None
    return max(session_dates)


def _status_counts(values: Sequence[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _merge_alerts(
    alert_groups: Sequence[Sequence[OperatorAlert | Mapping[str, Any]] | OperatorAlert | Mapping[str, Any]]
) -> tuple[OperatorAlert, ...]:
    merged: dict[str, OperatorAlert] = {}
    for group in alert_groups:
        if isinstance(group, (OperatorAlert, Mapping)):
            iterable: Sequence[OperatorAlert | Mapping[str, Any]] = (group,)
        else:
            iterable = group
        for alert in iterable:
            candidate = alert if isinstance(alert, OperatorAlert) else OperatorAlert(**dict(alert))
            existing = merged.get(candidate.code)
            if existing is None:
                merged[candidate.code] = candidate
            else:
                merged[candidate.code] = OperatorAlert(
                    code=existing.code,
                    severity=_max_severity(existing.severity, candidate.severity),
                    title=existing.title,
                    message=existing.message,
                    details={**existing.details, **candidate.details},
                )
    return tuple(merged.values())


def _max_severity(left: str, right: str) -> str:
    order = {"info": 0, "warning": 1, "critical": 2}
    return left if order.get(left, 0) >= order.get(right, 0) else right


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
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
