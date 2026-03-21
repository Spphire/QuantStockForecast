"""Shared strategy runtime helpers for legacy and managed paper execution."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from execution.common.execution_models import ExecutionPlan, PositionSnapshot, TargetPosition


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def parse_session_date(raw_value: str) -> date:
    return date.fromisoformat(raw_value)


def load_strategy_config(path: str | Path) -> dict:
    config_path = Path(path)
    return json.loads(config_path.read_text(encoding="utf-8"))


def runtime_dir(strategy_id: str, override: str = "") -> Path:
    if override:
        return Path(override)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return PROJECT_ROOT / "execution" / "runtime" / strategy_id / stamp


def latest_dir(strategy_id: str) -> Path:
    return PROJECT_ROOT / "execution" / "runtime" / strategy_id / "latest"


def default_ledger_path(strategy_id: str) -> Path:
    return PROJECT_ROOT / "artifacts" / "paper_trading" / strategy_id / "paper_ledger.sqlite3"


def load_target_frame(source_path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(source_path, encoding="utf-8-sig")
    if frame.empty:
        raise ValueError("No target positions found in source CSV.")
    return frame


def available_rebalance_dates(source_path: str | Path, actions_path: str | Path | None = None) -> list[str]:
    frame = load_target_frame(source_path)
    if "rebalance_date" not in frame.columns:
        raise ValueError("Target source CSV must contain a rebalance_date column.")
    dates = {
        str(value)
        for value in frame["rebalance_date"].dropna().astype(str).unique().tolist()
    }
    action_frame = load_actions_frame(actions_path or infer_actions_path(source_path))
    if action_frame is not None and "rebalance_date" in action_frame.columns:
        dates.update(
            str(value)
            for value in action_frame["rebalance_date"].dropna().astype(str).unique().tolist()
        )
    dates = sorted(dates)
    if not dates:
        raise ValueError("No rebalance_date values were found in source CSV.")
    return dates


def select_rebalance_date(frame: pd.DataFrame, rebalance_selection: str) -> str:
    selection = str(rebalance_selection or "latest").lower()
    if "rebalance_date" not in frame.columns:
        raise ValueError("Target source CSV must contain a rebalance_date column.")
    if selection == "latest":
        return str(frame["rebalance_date"].max())
    return selection


def load_target_positions(
    source_path: str | Path,
    rebalance_selection: str,
    *,
    actions_path: str | Path | None = None,
) -> list[TargetPosition]:
    frame = load_target_frame(source_path)
    rebalance_date = select_rebalance_date(frame, rebalance_selection)
    current = frame[frame["rebalance_date"].astype(str) == rebalance_date].copy()

    targets: list[TargetPosition] = []
    seen_symbols: set[str] = set()
    for _, row in current.iterrows():
        target = _target_position_from_row(row, rebalance_date=rebalance_date)
        targets.append(target)
        seen_symbols.add(target.symbol.upper())

    action_frame = load_actions_frame(actions_path or infer_actions_path(source_path))
    if action_frame is not None and "rebalance_date" in action_frame.columns:
        current_actions = action_frame[action_frame["rebalance_date"].astype(str) == rebalance_date].copy()
        for _, row in current_actions.iterrows():
            symbol = str(row.get("symbol", "")).strip()
            if not symbol:
                continue
            if symbol.upper() in seen_symbols:
                continue
            target_weight = _coerce_float(row.get("target_weight", 0.0))
            action = str(row.get("action", "")).strip().lower()
            if target_weight > 1e-9 and action != "exit":
                continue
            target = _target_position_from_row(row, rebalance_date=rebalance_date)
            targets.append(target)
            seen_symbols.add(target.symbol.upper())

    if not targets:
        raise ValueError(f"No rows found for rebalance date {rebalance_date}.")
    return targets


def load_local_positions(path: str | Path) -> list[PositionSnapshot]:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    positions: list[PositionSnapshot] = []
    for _, row in frame.iterrows():
        positions.append(
            PositionSnapshot(
                symbol=str(row.get("symbol", "")),
                qty=float(row.get("qty", 0.0) or 0.0),
                market_value=float(row.get("market_value", 0.0) or 0.0),
                current_price=float(row.get("current_price", 0.0) or 0.0),
            )
        )
    return positions


def save_plan(output_dir: Path, plan: ExecutionPlan) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    plan_json_path = output_dir / "execution_plan.json"
    targets_csv_path = output_dir / "target_positions.csv"
    intents_csv_path = output_dir / "order_intents.csv"

    plan_json_path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([item.to_dict() for item in plan.target_positions]).to_csv(
        targets_csv_path, index=False, encoding="utf-8"
    )
    pd.DataFrame([item.to_dict() for item in plan.order_intents]).to_csv(
        intents_csv_path, index=False, encoding="utf-8"
    )
    return {
        "plan_json_path": str(plan_json_path),
        "targets_csv_path": str(targets_csv_path),
        "intents_csv_path": str(intents_csv_path),
    }


def sync_latest_run(strategy_id: str, run_dir: Path) -> Path:
    latest_path = latest_dir(strategy_id)
    latest_path.mkdir(parents=True, exist_ok=True)
    for filename in [
        "execution_plan.json",
        "target_positions.csv",
        "order_intents.csv",
        "run_summary.json",
        "submitted_orders.json",
        "submission_attempts.json",
        "submitted_order_statuses.json",
        "pre_account_snapshot.json",
        "pre_positions_snapshot.json",
        "post_account_snapshot.json",
        "post_positions_snapshot.json",
    ]:
        source = run_dir / filename
        if source.exists():
            target = latest_path / filename
            target.write_bytes(source.read_bytes())
    return latest_path


def normalized_buffer(raw_value: object) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = 1.0
    return min(max(value, 0.0), 1.0)


def infer_actions_path(source_path: str | Path) -> Path:
    return Path(source_path).with_name("risk_actions.csv")


def load_actions_frame(path: str | Path | None) -> pd.DataFrame | None:
    if path in (None, ""):
        return None
    resolved = Path(path)
    if not resolved.exists():
        return None
    frame = pd.read_csv(resolved, encoding="utf-8-sig")
    return frame if not frame.empty else None


def _target_position_from_row(row: pd.Series, *, rebalance_date: str) -> TargetPosition:
    return TargetPosition(
        symbol=str(row.get("symbol", "")),
        target_weight=_coerce_float(row.get("target_weight", row.get("weight", 0.0))),
        previous_weight=_coerce_float(row.get("previous_weight", 0.0)),
        action=str(row.get("action", "")),
        reference_price=_row_reference_price(row),
        score=_coerce_float(row.get("score", 0.0)),
        confidence=_coerce_float(row.get("confidence", 0.0)),
        rebalance_date=rebalance_date,
        metadata={
            "model_mode": row.get("model_mode", ""),
            "industry_group": row.get("industry_group", ""),
            "name": row.get("name", ""),
        },
    )


def _row_reference_price(row: pd.Series) -> float:
    for key in ("close", "reference_price", "current_price", "last_price", "open"):
        value = _coerce_float(row.get(key), default=None)
        if value is not None and value > 0:
            return value
    return 0.0


def _coerce_float(value: Any, default: float | None = 0.0) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
