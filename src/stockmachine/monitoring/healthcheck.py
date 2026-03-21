from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from pandas.errors import EmptyDataError

from stockmachine.monitoring.alerts import TERMINAL_ORDER_STATUSES


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE_ROOT = PROJECT_ROOT / "execution" / "state"


@dataclass(slots=True, frozen=True)
class PaperDailyHealthcheckResult:
    healthy: bool
    reasons: tuple[str, ...]
    state_readable: bool
    state_path: str
    latest_state: Mapping[str, Any] | None
    latest_runtime_dir: str | None
    open_orders_total: int
    open_orders_for_latest_run: int
    order_journal_rows: int
    data_freshness_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "reasons": list(self.reasons),
            "state_readable": self.state_readable,
            "state_path": self.state_path,
            "latest_state": dict(self.latest_state) if self.latest_state is not None else None,
            "latest_runtime_dir": self.latest_runtime_dir,
            "open_orders_total": self.open_orders_total,
            "open_orders_for_latest_run": self.open_orders_for_latest_run,
            "order_journal_rows": self.order_journal_rows,
            "data_freshness_meta": dict(self.data_freshness_meta),
        }


def build_paper_daily_healthcheck(
    strategy_id: str,
    *,
    state_root: str | Path | None = None,
    reference_date: date | None = None,
) -> PaperDailyHealthcheckResult:
    resolved_root = Path(state_root) if state_root is not None else DEFAULT_STATE_ROOT
    state_dir = resolved_root / strategy_id
    latest_state_path = state_dir / "latest_state.json"
    reasons: list[str] = []
    latest_state: dict[str, Any] | None = None
    data_freshness_meta: dict[str, Any] = {"strategy_id": strategy_id, "state_dir": str(state_dir)}
    open_orders_total = 0
    open_orders_for_latest_run = 0
    order_journal_rows = 0
    state_readable = False
    latest_runtime_dir: str | None = None

    try:
        if latest_state_path.exists():
            payload = json.loads(latest_state_path.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                latest_state = dict(payload)
                state_readable = True
            else:
                reasons.append("invalid_latest_state")
        else:
            reasons.append("missing_latest_state")

        if latest_state is not None:
            latest_runtime_dir = str(latest_state.get("latest_runtime_dir") or latest_state.get("run_dir") or "")
            order_journal_path = state_dir / "order_journal.csv"
            if order_journal_path.exists():
                try:
                    order_journal = pd.read_csv(order_journal_path, encoding="utf-8-sig")
                except EmptyDataError:
                    order_journal = pd.DataFrame()
                order_journal_rows = int(len(order_journal))

            statuses = _load_statuses(latest_state.get("submitted_order_statuses_path"))
            open_orders_total = len(statuses)
            open_orders_for_latest_run = len(
                [item for item in statuses if str(item.get("status", "")).lower() not in TERMINAL_ORDER_STATUSES]
            )
            if open_orders_for_latest_run > 0:
                reasons.append("lingering_open_orders")

            session_date = _parse_date(
                latest_state.get("rebalance_date")
                or latest_state.get("session_date")
                or latest_state.get("effective_session_date")
            )
            if session_date is not None:
                ref = reference_date or date.today()
                lag_days = (ref - session_date).days
                data_freshness_meta.update(
                    {
                        "session_date": session_date.isoformat(),
                        "session_lag_days": lag_days,
                        "exact_session_match": lag_days == 0,
                    }
                )
                if lag_days >= 2:
                    reasons.append("stale_session_date")
    except Exception as exc:
        reasons.append(type(exc).__name__)
        return PaperDailyHealthcheckResult(
            healthy=False,
            reasons=tuple(reasons),
            state_readable=False,
            state_path=str(latest_state_path),
            latest_state=None,
            latest_runtime_dir=None,
            open_orders_total=0,
            open_orders_for_latest_run=0,
            order_journal_rows=0,
            data_freshness_meta={"error": str(exc), **data_freshness_meta},
        )

    healthy = state_readable and not reasons
    return PaperDailyHealthcheckResult(
        healthy=healthy,
        reasons=tuple(reasons),
        state_readable=state_readable,
        state_path=str(latest_state_path),
        latest_state=latest_state,
        latest_runtime_dir=latest_runtime_dir,
        open_orders_total=open_orders_total,
        open_orders_for_latest_run=open_orders_for_latest_run,
        order_journal_rows=order_journal_rows,
        data_freshness_meta=data_freshness_meta,
    )


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


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
