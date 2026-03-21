from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from execution.alpaca.account_monitor import save_account_snapshot
from execution.alpaca.client import AlpacaBroker, load_alpaca_credentials
from execution.alpaca.order_router import submit_execution_plan
from execution.common.execution_models import ExecutionPlan, OrderIntent, PositionSnapshot, TargetPosition
from execution.common.order_safety import validate_execution_plan
from execution.common.reconciliation import build_order_intents, normalize_current_weights
from execution.common.state_store import write_latest_state, write_order_journal
from execution.common.strategy_runtime import (
    available_rebalance_dates,
    default_ledger_path,
    load_local_positions,
    load_strategy_config,
    load_target_positions,
    normalized_buffer,
    parse_session_date,
    runtime_dir,
    save_plan,
    sync_latest_run,
)
from stockmachine.live.reconciler import PollingOrderReconciler
from stockmachine.live.recovery import recover_open_orders
from stockmachine.live.session_guard import SessionGuard, SessionGuardRequest
from stockmachine.monitoring.reports import (
    PaperRunFailure,
    build_paper_run_manifest,
    build_paper_run_report,
)
from stockmachine.risk.paper import BrokerAwareOrderRiskPolicy
from stockmachine.state.ledger import LocalLedger
from stockmachine.state.models import EquitySnapshotRecord, OrderDecisionRecord, RunRecord, TargetRecord


@dataclass(slots=True, frozen=True)
class ManagedPaperRunResult:
    report: Mapping[str, Any]
    summary: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": dict(self.report),
            "summary": dict(self.summary),
        }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the productized multi-expert paper-execution flow.")
    parser.add_argument("strategy_config", help="Path to one execution strategy JSON config.")
    parser.add_argument("--session-date", default="", help="Optional target rebalance date override.")
    parser.add_argument("--submit", action="store_true", help="Submit approved orders to Alpaca.")
    parser.add_argument("--account-equity", type=float, default=0.0, help="Dry-run account equity override.")
    parser.add_argument("--current-positions-csv", default="", help="Optional dry-run current positions CSV.")
    parser.add_argument("--output-dir", default="", help="Optional runtime output directory override.")
    parser.add_argument("--ledger-path", default="", help="Optional SQLite ledger path override.")
    parser.add_argument("--output-format", choices=("json", "text"), default="json")
    parser.add_argument("--skip-session-guard", action="store_true", help="Skip duplicate/data-date preflight.")
    parser.add_argument("--require-paper", action="store_true", help="Block execution unless the broker endpoint is paper.")
    parser.add_argument("--post-submit-poll-seconds", type=float, default=15.0)
    parser.add_argument("--post-submit-poll-interval-seconds", type=float, default=2.0)
    return parser


def run_strategy(
    strategy_config_path: str | Path,
    *,
    session_date_override: str = "",
    submit: bool = False,
    account_equity_override: float = 0.0,
    current_positions_csv: str = "",
    output_dir: str = "",
    ledger_path: str = "",
    skip_session_guard: bool = False,
    require_paper: bool = False,
    post_submit_poll_seconds: float = 15.0,
    post_submit_poll_interval_seconds: float = 2.0,
) -> ManagedPaperRunResult:
    strategy_config = load_strategy_config(strategy_config_path)
    strategy_id = str(strategy_config["strategy_id"])
    source = dict(strategy_config.get("source", {}))
    execution_config = dict(strategy_config.get("execution", {}))
    source_path = str(source.get("path", ""))
    if source.get("type") != "risk_positions_csv" or not source_path:
        raise ValueError("Managed paper runner currently supports strategy source.type=risk_positions_csv only.")

    rebalance_selection = (
        session_date_override.strip()
        if session_date_override.strip()
        else str(execution_config.get("rebalance_selection", "latest"))
    )
    targets = load_target_positions(
        source_path,
        rebalance_selection=rebalance_selection,
        actions_path=source.get("actions_path", ""),
    )
    target_session_date = parse_session_date(targets[0].rebalance_date)
    available_dates = tuple(
        parse_session_date(raw)
        for raw in available_rebalance_dates(source_path, actions_path=source.get("actions_path", ""))
    )

    effective_ledger_path = Path(ledger_path) if ledger_path else default_ledger_path(strategy_id)
    run_dir = runtime_dir(strategy_id, output_dir)
    broker_name = str(strategy_config.get("broker", "alpaca"))
    run_id = uuid4().hex
    failures: list[PaperRunFailure] = []

    with LocalLedger(effective_ledger_path) as ledger:
        ledger.initialize()
        ledger.record_run(
            RunRecord(
                run_id=run_id,
                strategy_name=strategy_id,
                market=str(strategy_config.get("market", "US")),
                created_at_utc=datetime.now(timezone.utc),
                status="running",
                meta={
                    "strategy_config_path": str(Path(strategy_config_path)),
                    "source_path": source_path,
                    "session_date": target_session_date.isoformat(),
                    "run_mode": "execute" if submit else "dry_run",
                },
            )
        )

        session_guard_result = None
        effective_session_date = target_session_date
        if not skip_session_guard:
            session_guard_result = SessionGuard(ledger).evaluate(
                SessionGuardRequest(
                    ledger=ledger,
                    strategy_name=strategy_id,
                    session_date=target_session_date,
                    dry_run=not submit,
                    silver_session_dates=available_dates,
                    allow_previous_available_session=True,
                )
            )
            if session_guard_result.effective_session_date is not None:
                effective_session_date = session_guard_result.effective_session_date
            if not session_guard_result.allowed:
                manifest = build_paper_run_manifest(
                    run_id=run_id,
                    session_date=effective_session_date,
                    strategy_name=strategy_id,
                    model_name=_infer_model_name(targets, strategy_id),
                    dry_run=not submit,
                    data_snapshot=_data_snapshot_payload(
                        source_path=source_path,
                        source_summary_path=str(source.get("summary_path", "")),
                        requested_session_date=target_session_date,
                        effective_session_date=effective_session_date,
                        available_dates=available_dates,
                        session_guard=session_guard_result.to_dict(),
                    ),
                    risk_policy={"source": "risk_positions_csv"},
                    execution_policy=_execution_policy_payload(execution_config),
                    meta={"strategy_config_path": str(Path(strategy_config_path))},
                )
                ledger.record_run_manifest(manifest.to_record())
                ledger.finish_run(run_id, finished_at_utc=datetime.now(timezone.utc), status="blocked")
                report = build_paper_run_report(
                    session_date=effective_session_date,
                    dry_run=not submit,
                    stage="preflight_blocked",
                    counts={"targets": len(targets), "orders": 0, "submitted_orders": 0},
                    failures=tuple(
                        PaperRunFailure(stage="session_guard", reason=reason, details=session_guard_result.to_dict())
                        for reason in session_guard_result.reasons
                    ),
                    meta={"session_guard": session_guard_result.to_dict()},
                    run_id=run_id,
                    manifest=manifest,
                )
                summary = {
                    "strategy_id": strategy_id,
                    "run_id": run_id,
                    "rebalance_date": effective_session_date.isoformat(),
                    "submit_mode": submit,
                    "blocked": True,
                    "ledger_path": str(effective_ledger_path),
                    "session_guard": session_guard_result.to_dict(),
                    "run_dir": str(run_dir),
                }
                _write_blocked_state(strategy_id, summary)
                return ManagedPaperRunResult(report=report.to_dict(), summary=summary)

        broker = None
        account = None
        account_buying_power = 0.0
        if submit:
            credentials = load_alpaca_credentials(str(strategy_config["paper_env_prefix"]))
            broker = AlpacaBroker(credentials)
            if require_paper and not broker.is_paper_trading_environment():
                raise RuntimeError(
                    f"Refusing to submit non-paper orders for {strategy_id}: {broker.credentials.base_url}"
                )
            account = broker.get_account_snapshot()
            current_positions = normalize_current_weights(
                broker.list_positions(),
                account_equity=account.equity,
            )
            account_buying_power = account.buying_power
        else:
            account_equity = (
                account_equity_override
                if account_equity_override > 0
                else float(execution_config.get("default_account_equity", 100000.0))
            )
            account_buying_power = account_equity
            current_positions = normalize_current_weights(
                load_local_positions(current_positions_csv) if current_positions_csv else [],
                account_equity=account_equity,
            )

        account_equity = float(account.equity) if account is not None else float(account_buying_power)
        buying_power_buffer = normalized_buffer(execution_config.get("buying_power_buffer", 1.0))
        planning_equity = account_equity * buying_power_buffer
        order_intents = build_order_intents(
            targets,
            current_positions,
            account_equity=account_equity,
            planning_equity=planning_equity,
            allow_fractional=bool(execution_config.get("allow_fractional", True)),
            order_sizing_mode=str(execution_config.get("order_sizing_mode", "notional")),
            order_type=str(execution_config.get("order_type", "market")),
            time_in_force=str(execution_config.get("time_in_force", "day")),
        )
        plan = ExecutionPlan(
            strategy_id=strategy_id,
            broker=broker_name,
            rebalance_date=effective_session_date.isoformat(),
            generated_at=datetime.now(timezone.utc).isoformat(),
            account_equity=account_equity,
            planning_equity=planning_equity,
            account_buying_power=account_buying_power,
            current_positions=current_positions,
            target_positions=targets,
            order_intents=order_intents,
            notes=[],
        )
        if buying_power_buffer < 1.0:
            plan.notes.append(
                f"Apply buying_power_buffer={buying_power_buffer:.4f}; planning_equity={planning_equity:.2f}."
            )
        plan = validate_execution_plan(
            plan,
            max_position_weight=float(execution_config.get("max_position_weight", 1.0)),
            min_order_notional=float(execution_config.get("min_order_notional", 0.0)),
        )

        saved_plan_paths = save_plan(run_dir, plan)
        latest_runtime_path = sync_latest_run(strategy_id, run_dir)
        manifest = build_paper_run_manifest(
            run_id=run_id,
            session_date=effective_session_date,
            strategy_name=strategy_id,
            model_name=_infer_model_name(targets, strategy_id),
            dry_run=not submit,
            data_snapshot=_data_snapshot_payload(
                source_path=source_path,
                source_summary_path=str(source.get("summary_path", "")),
                requested_session_date=target_session_date,
                effective_session_date=effective_session_date,
                available_dates=available_dates,
                session_guard=session_guard_result.to_dict() if session_guard_result is not None else {},
            ),
            risk_policy={"source": "risk_positions_csv"},
            execution_policy=_execution_policy_payload(execution_config),
            meta={
                "strategy_config_path": str(Path(strategy_config_path)),
                "runtime_dir": str(run_dir),
                "latest_runtime_dir": str(latest_runtime_path),
                "poll_seconds": post_submit_poll_seconds,
                "poll_interval_seconds": post_submit_poll_interval_seconds,
            },
        )
        ledger.record_run_manifest(manifest.to_record())
        _record_targets(ledger, run_id=run_id, session_date=effective_session_date, targets=targets)
        if not submit:
            _record_order_decisions(
                ledger,
                run_id=run_id,
                session_date=effective_session_date,
                orders=plan.order_intents,
                approved_orders=plan.order_intents,
                issues=(),
                run_tag=run_id[:8],
            )

        submitted_orders: list[dict[str, Any]] = []
        attempt_logs: list[dict[str, Any]] = []
        order_statuses: list[dict[str, Any]] = []
        snapshot_paths: dict[str, str] = {}
        recovery_summary: dict[str, Any] = {}
        validation_summary: dict[str, Any] = {
            "approved_count": len(plan.order_intents),
            "blocked_count": 0,
            "issues": [],
        }
        if submit and broker is not None and account is not None:
            snapshot_paths.update(save_account_snapshot(broker, run_dir, prefix="pre"))
            clock_payload = broker.get_clock()
            _record_equity_snapshot(
                ledger,
                run_id=run_id,
                session_date=effective_session_date,
                account_payload=account.raw,
                account_equity=account.equity,
                account_cash=account.cash,
                current_positions=current_positions,
            )

            open_orders = tuple(broker.list_orders(status="open"))
            recovery_result = recover_open_orders(
                ledger,
                open_orders,
                reconciler=PollingOrderReconciler(ledger),
            )
            recovery_summary = {
                "aligned_open_orders": recovery_result.plan.aligned_count,
                "orphan_broker_orders": recovery_result.plan.orphan_count,
                "stale_ledger_orders": recovery_result.plan.stale_count,
                "reconciled_created_orders": recovery_result.reconciliation.created_orders,
                "reconciled_updated_orders": recovery_result.reconciliation.updated_orders,
                "reconciled_fill_events": recovery_result.reconciliation.fill_events_created,
            }

            risk_policy = BrokerAwareOrderRiskPolicy(
                require_market_open=bool(execution_config.get("require_market_open", False)),
                require_client_order_id=False,
                min_buying_power_buffer=float(execution_config.get("min_buying_power_buffer", 0.0)),
                max_order_notional=_coerce_optional_float(execution_config.get("max_order_notional")),
                max_total_notional=_coerce_optional_float(execution_config.get("max_total_notional")),
                max_total_orders=_coerce_optional_int(execution_config.get("max_total_orders")),
            )
            validation = risk_policy.validate(
                orders=plan.order_intents,
                account_sync=_account_sync_payload(account.raw, clock_payload),
                open_orders=open_orders,
            )
            validation_summary = {
                "approved_count": len(validation.approved_orders),
                "blocked_count": len(validation.blocked_orders),
                "issues": [issue.to_dict() if hasattr(issue, "to_dict") else asdict(issue) for issue in validation.issues],
            }
            _record_order_decisions(
                ledger,
                run_id=run_id,
                session_date=effective_session_date,
                orders=plan.order_intents,
                approved_orders=validation.approved_orders,
                issues=validation.issues,
                run_tag=run_id[:8],
            )

            approved_plan = ExecutionPlan(
                strategy_id=plan.strategy_id,
                broker=plan.broker,
                rebalance_date=plan.rebalance_date,
                generated_at=plan.generated_at,
                account_equity=plan.account_equity,
                planning_equity=plan.planning_equity,
                account_buying_power=plan.account_buying_power,
                current_positions=plan.current_positions,
                target_positions=plan.target_positions,
                order_intents=list(validation.approved_orders),
                notes=list(plan.notes),
            )
            if validation.blocked_orders:
                approved_plan.notes.append(
                    f"Blocked {len(validation.blocked_orders)} orders with broker-aware risk policy."
                )

            submission_result = submit_execution_plan(
                broker,
                approved_plan,
                cancel_open_orders_first=bool(execution_config.get("cancel_open_orders_first", True)),
                buy_retry_shrink_ratio=float(execution_config.get("buy_retry_shrink_ratio", 0.97)),
                max_buy_retries=int(execution_config.get("max_buy_retries", 1)),
                refresh_status_after_submit=bool(execution_config.get("refresh_status_after_submit", True)),
            )
            submitted_orders = [item.to_dict() for item in submission_result["submitted_orders"]]
            attempt_logs = [dict(item) for item in submission_result["attempt_logs"]]
            order_statuses = [dict(item) for item in submission_result["order_statuses"]]

            (run_dir / "submitted_orders.json").write_text(
                json.dumps(submitted_orders, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (run_dir / "submission_attempts.json").write_text(
                json.dumps(attempt_logs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (run_dir / "submitted_order_statuses.json").write_text(
                json.dumps(order_statuses, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if order_statuses:
                PollingOrderReconciler(ledger).reconcile_orders(order_statuses)
            snapshot_paths.update(save_account_snapshot(broker, run_dir, prefix="post"))

        summary = {
            "strategy_id": strategy_id,
            "run_id": run_id,
            "broker": broker_name,
            "rebalance_date": effective_session_date.isoformat(),
            "account_equity": account_equity,
            "planning_equity": planning_equity,
            "account_buying_power": account_buying_power,
            "buying_power_buffer": buying_power_buffer,
            "target_count": len(plan.target_positions),
            "order_count": len(plan.order_intents),
            "submit_mode": submit,
            "submitted_count": len(submitted_orders),
            "attempt_count": len(attempt_logs),
            "status_snapshot_count": len(order_statuses),
            "plan_json_path": saved_plan_paths["plan_json_path"],
            "targets_csv_path": saved_plan_paths["targets_csv_path"],
            "intents_csv_path": saved_plan_paths["intents_csv_path"],
            "notes": list(plan.notes),
            "source_summary_path": str(source.get("summary_path", "")),
            "run_dir": str(run_dir),
            "latest_runtime_dir": str(latest_runtime_path),
            "submitted_orders_path": str(run_dir / "submitted_orders.json") if submitted_orders else "",
            "submission_attempts_path": str(run_dir / "submission_attempts.json") if attempt_logs else "",
            "submitted_order_statuses_path": str(run_dir / "submitted_order_statuses.json") if order_statuses else "",
            "ledger_path": str(effective_ledger_path),
            "session_guard": session_guard_result.to_dict() if session_guard_result is not None else {},
            "recovery": recovery_summary,
            "validation": validation_summary,
            **snapshot_paths,
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        order_rows = _build_order_rows(
            strategy_id=strategy_id,
            rebalance_date=effective_session_date.isoformat(),
            generated_at=plan.generated_at,
            run_dir=run_dir,
            attempt_logs=attempt_logs,
            order_statuses=order_statuses,
            submitted_orders=submitted_orders,
        )
        state_summary = write_latest_state(strategy_id, summary)
        order_journal_path = write_order_journal(strategy_id, order_rows)
        summary["latest_state_path"] = state_summary["latest_state_path"]
        summary["order_journal_path"] = order_journal_path

        if submit and validation_summary["blocked_count"] > 0:
            failures.append(
                PaperRunFailure(
                    stage="broker_risk_gate",
                    reason="orders_blocked",
                    details=validation_summary,
                )
            )
        if submit and any(str(item.get("latest_status", "")).lower() == "rejected" for item in order_rows):
            failures.append(
                PaperRunFailure(
                    stage="submission",
                    reason="broker_rejection",
                    details={"order_rows": order_rows},
                )
            )

        report = build_paper_run_report(
            session_date=effective_session_date,
            dry_run=not submit,
            stage="completed",
            counts={
                "targets": len(plan.target_positions),
                "orders": len(plan.order_intents),
                "submitted_orders": len(submitted_orders),
                "blocked_orders": int(validation_summary["blocked_count"]),
            },
            failures=tuple(failures),
            meta={
                "strategy_config_path": str(Path(strategy_config_path)),
                "summary_path": str(run_dir / "run_summary.json"),
                "session_guard": session_guard_result.to_dict() if session_guard_result is not None else {},
                "recovery": recovery_summary,
                "validation": validation_summary,
            },
            run_id=run_id,
            manifest=manifest,
        )
        ledger.finish_run(
            run_id,
            finished_at_utc=datetime.now(timezone.utc),
            status="finished" if not failures else "completed_with_findings",
        )
        return ManagedPaperRunResult(report=report.to_dict(), summary=summary)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    result = run_strategy(
        args.strategy_config,
        session_date_override=args.session_date,
        submit=args.submit,
        account_equity_override=args.account_equity,
        current_positions_csv=args.current_positions_csv,
        output_dir=args.output_dir,
        ledger_path=args.ledger_path,
        skip_session_guard=args.skip_session_guard,
        require_paper=args.require_paper,
        post_submit_poll_seconds=args.post_submit_poll_seconds,
        post_submit_poll_interval_seconds=args.post_submit_poll_interval_seconds,
    )
    if args.output_format == "json":
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=_json_default))
    else:
        _print_text_result(result)
    return 0


def _record_targets(
    ledger: LocalLedger,
    *,
    run_id: str,
    session_date: date,
    targets: Sequence[TargetPosition],
) -> None:
    timestamp = datetime.now(timezone.utc)
    for target in targets:
        ledger.append_target(
            TargetRecord(
                run_id=run_id,
                session_date=session_date,
                symbol=target.symbol,
                target_weight=target.target_weight,
                max_weight=max(target.target_weight, 0.0),
                reason=target.action or "target",
                timestamp_utc=timestamp,
                meta={
                    "previous_weight": target.previous_weight,
                    "reference_price": target.reference_price,
                    "score": target.score,
                    "confidence": target.confidence,
                    "metadata": dict(target.metadata),
                },
            )
        )


def _record_equity_snapshot(
    ledger: LocalLedger,
    *,
    run_id: str,
    session_date: date,
    account_payload: Mapping[str, Any],
    account_equity: float,
    account_cash: float,
    current_positions: Sequence[PositionSnapshot],
) -> None:
    gross_exposure = sum(abs(position.market_value) for position in current_positions)
    ledger.record_equity_snapshot(
        EquitySnapshotRecord(
            run_id=run_id,
            session_date=session_date,
            timestamp_utc=datetime.now(timezone.utc),
            cash=account_cash,
            equity=account_equity,
            gross_exposure=gross_exposure,
            payload={
                "account": dict(account_payload),
                "positions": [position.to_dict() for position in current_positions],
            },
        )
    )


def _record_order_decisions(
    ledger: LocalLedger,
    *,
    run_id: str,
    session_date: date,
    orders: Sequence[OrderIntent],
    approved_orders: Sequence[OrderIntent],
    issues: Sequence[object],
    run_tag: str,
) -> None:
    approved_keys = {_order_key(order) for order in approved_orders}
    issues_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        payload = issue.to_dict() if hasattr(issue, "to_dict") else asdict(issue)
        symbol = str(payload.get("symbol") or "")
        issues_by_symbol.setdefault(symbol, []).append(payload)

    decision_time = datetime.now(timezone.utc)
    for index, order in enumerate(orders, start=1):
        symbol_issues = issues_by_symbol.get(order.symbol.upper(), []) + issues_by_symbol.get(order.symbol, [])
        approved = _order_key(order) in approved_keys
        decision_reason = "approved" if approved else ",".join(
            issue.get("code", issue.get("reason", "blocked")) for issue in symbol_issues
        ) or "blocked"
        ledger.record_order_decision(
            OrderDecisionRecord(
                decision_id=f"{run_id}:{index:04d}",
                run_id=run_id,
                session_date=session_date,
                client_order_id=_planned_client_order_id(
                    strategy_run_tag=run_tag,
                    session_date=session_date,
                    symbol=order.symbol,
                    side=order.side,
                    sequence=index,
                ),
                symbol=order.symbol,
                side=order.side.upper(),
                decision_type=order.submit_as,
                decision_price=order.reference_price or None,
                estimated_notional=_estimate_order_notional(order),
                approved=approved,
                reason=decision_reason,
                decision_at_utc=decision_time,
                meta={
                    "order": order.to_dict(),
                    "issues": symbol_issues,
                },
            )
        )


def _build_order_rows(
    *,
    strategy_id: str,
    rebalance_date: str,
    generated_at: str,
    run_dir: Path,
    attempt_logs: Sequence[Mapping[str, Any]],
    order_statuses: Sequence[Mapping[str, Any]],
    submitted_orders: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    status_by_order_id = {
        str(item.get("id", "")): str(item.get("status", ""))
        for item in order_statuses
        if str(item.get("id", ""))
    }
    source_rows = list(attempt_logs) if attempt_logs else list(submitted_orders)
    order_rows: list[dict[str, Any]] = []
    for item in source_rows:
        row = dict(item)
        order_id = str(row.get("order_id", ""))
        if order_id:
            row["latest_status"] = status_by_order_id.get(order_id, row.get("status", ""))
        row["strategy_id"] = strategy_id
        row["rebalance_date"] = rebalance_date
        row["generated_at"] = generated_at
        row["run_dir"] = str(run_dir)
        order_rows.append(row)
    return order_rows


def _planned_client_order_id(
    *,
    strategy_run_tag: str,
    session_date: date,
    symbol: str,
    side: str,
    sequence: int,
) -> str:
    compact_symbol = symbol.upper().replace(".", "")[:8]
    compact_side = side.upper()[:4]
    return f"qsf-{session_date:%Y%m%d}-{compact_symbol}-{compact_side}-{sequence:04d}-{strategy_run_tag}"


def _data_snapshot_payload(
    *,
    source_path: str,
    source_summary_path: str,
    requested_session_date: date,
    effective_session_date: date,
    available_dates: Sequence[date],
    session_guard: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "source_path": source_path,
        "source_summary_path": source_summary_path,
        "requested_session_date": requested_session_date.isoformat(),
        "effective_session_date": effective_session_date.isoformat(),
        "available_session_count": len(available_dates),
        "first_available_session_date": available_dates[0].isoformat() if available_dates else None,
        "last_available_session_date": available_dates[-1].isoformat() if available_dates else None,
        "session_guard": dict(session_guard),
    }


def _execution_policy_payload(execution_config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "allow_fractional": bool(execution_config.get("allow_fractional", True)),
        "order_sizing_mode": str(execution_config.get("order_sizing_mode", "notional")),
        "buying_power_buffer": normalized_buffer(execution_config.get("buying_power_buffer", 1.0)),
        "buy_retry_shrink_ratio": float(execution_config.get("buy_retry_shrink_ratio", 0.97)),
        "max_buy_retries": int(execution_config.get("max_buy_retries", 1)),
        "refresh_status_after_submit": bool(execution_config.get("refresh_status_after_submit", True)),
        "min_order_notional": float(execution_config.get("min_order_notional", 0.0)),
        "max_position_weight": float(execution_config.get("max_position_weight", 1.0)),
        "order_type": str(execution_config.get("order_type", "market")),
        "time_in_force": str(execution_config.get("time_in_force", "day")),
        "cancel_open_orders_first": bool(execution_config.get("cancel_open_orders_first", True)),
        "max_order_notional": _coerce_optional_float(execution_config.get("max_order_notional")),
        "max_total_notional": _coerce_optional_float(execution_config.get("max_total_notional")),
        "max_total_orders": _coerce_optional_int(execution_config.get("max_total_orders")),
    }


def _account_sync_payload(account_payload: Mapping[str, Any], clock_payload: Mapping[str, Any]) -> object:
    return type(
        "AccountSyncPayload",
        (),
        {
            "broker_account": type(
                "BrokerAccountPayload",
                (),
                {
                    "status": str(account_payload.get("status", "")),
                    "buying_power": float(account_payload.get("buying_power", 0.0) or 0.0),
                    "trading_blocked": bool(account_payload.get("trading_blocked", False)),
                    "account_blocked": bool(account_payload.get("account_blocked", False)),
                },
            )(),
            "clock": type(
                "BrokerClockPayload",
                (),
                {
                    "is_open": bool(clock_payload.get("is_open", False)),
                },
            )(),
        },
    )()


def _estimate_order_notional(order: OrderIntent) -> float:
    if order.submit_as == "notional" and order.submit_notional > 0:
        return float(order.submit_notional)
    if order.submit_qty > 0 and order.reference_price > 0:
        return float(order.submit_qty) * float(order.reference_price)
    if order.estimated_qty > 0 and order.reference_price > 0:
        return float(order.estimated_qty) * float(order.reference_price)
    return abs(float(order.delta_notional))


def _order_key(order: OrderIntent) -> tuple[str, str, str]:
    return (order.symbol.upper(), order.side.upper(), order.reason)


def _infer_model_name(targets: Sequence[TargetPosition], fallback: str) -> str:
    if not targets:
        return fallback
    model_mode = str(targets[0].metadata.get("model_mode", "")).strip()
    return model_mode or fallback


def _coerce_optional_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    return float(value)


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    return int(value)


def _write_blocked_state(strategy_id: str, summary: Mapping[str, Any]) -> None:
    write_latest_state(strategy_id, dict(summary))


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return value


def _print_text_result(result: ManagedPaperRunResult) -> None:
    summary = result.summary
    report = result.report
    print(f"[OK] Strategy: {summary.get('strategy_id', '')}")
    print(f"[INFO] Run id: {summary.get('run_id', '')}")
    print(f"[INFO] Rebalance date: {summary.get('rebalance_date', '')}")
    print(f"[INFO] Submit mode: {summary.get('submit_mode', False)}")
    print(f"[INFO] Plan path: {summary.get('plan_json_path', '')}")
    print(f"[INFO] Ledger path: {summary.get('ledger_path', '')}")
    print(f"[INFO] Report status: {report.get('status', '')}")
    print(f"[INFO] Submitted count: {summary.get('submitted_count', 0)}")
    print(f"[INFO] Blocked count: {summary.get('validation', {}).get('blocked_count', 0)}")


if __name__ == "__main__":
    raise SystemExit(main())
