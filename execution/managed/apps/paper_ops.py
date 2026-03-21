from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from execution.common.strategy_runtime import default_ledger_path, load_strategy_config
from execution.managed.monitoring.alerts import build_operator_alerts
from execution.managed.monitoring.healthcheck import build_paper_daily_healthcheck
from execution.managed.monitoring.reports import PaperRunFailure, build_paper_run_report
from execution.managed.state.ledger import LocalLedger


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect the managed paper ledger and emit JSON.")
    parser.add_argument("strategy_config", help="Path to one execution strategy JSON config.")
    parser.add_argument("--ledger-path", default="", help="Optional SQLite ledger path override.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("latest-run", help="Show the latest run summary.")
    subparsers.add_parser("open-orders", help="Show open orders from the latest run.")
    run_summary = subparsers.add_parser("run-summary", help="Show one run summary.")
    run_summary.add_argument("--run-id", required=True)
    return parser


def dispatch_command(args: argparse.Namespace) -> dict[str, Any]:
    strategy_config = load_strategy_config(args.strategy_config)
    strategy_id = str(strategy_config["strategy_id"])
    ledger_path = Path(args.ledger_path) if args.ledger_path else default_ledger_path(strategy_id)
    state_payload = _latest_state_payload(strategy_id)
    with LocalLedger(ledger_path) as ledger:
        ledger.initialize()
        if args.command == "latest-run":
            return build_latest_run_payload(ledger, ledger_path=ledger_path, state_payload=state_payload)
        if args.command == "open-orders":
            return build_open_orders_payload(ledger, ledger_path=ledger_path, state_payload=state_payload)
        return build_run_summary_payload(ledger, run_id=args.run_id, ledger_path=ledger_path, state_payload=state_payload)


def build_latest_run_payload(
    ledger: LocalLedger,
    *,
    ledger_path: Path,
    state_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifests = ledger.list_run_manifests()
    if not manifests:
        return {
            "command": "latest-run",
            "ledger_path": str(ledger_path),
            "run_id": None,
            "summary": {"message": "ledger is empty"},
            "alerts": [],
            "latest_state": _json_safe(state_payload) if state_payload else None,
        }
    return build_run_summary_payload(
        ledger,
        run_id=manifests[0].run_id,
        ledger_path=ledger_path,
        command="latest-run",
        state_payload=state_payload,
    )


def build_open_orders_payload(
    ledger: LocalLedger,
    *,
    ledger_path: Path,
    state_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifests = ledger.list_run_manifests()
    run_id = manifests[0].run_id if manifests else None
    orders = ledger.list_open_orders(run_id=run_id) if run_id is not None else []
    return {
        "command": "open-orders",
        "ledger_path": str(ledger_path),
        "run_id": run_id,
        "count": len(orders),
        "open_orders": [_json_safe(order) for order in orders],
        "latest_state": _json_safe(state_payload) if state_payload else None,
    }


def build_run_summary_payload(
    ledger: LocalLedger,
    *,
    run_id: str,
    ledger_path: Path,
    command: str = "run-summary",
    state_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run = ledger.get_run(run_id)
    manifest = ledger.get_run_manifest(run_id)
    orders = ledger.list_orders(run_id=run_id)
    open_orders = ledger.list_open_orders(run_id=run_id)
    fills = ledger.list_fills(run_id=run_id)
    failures: list[PaperRunFailure] = []
    if open_orders:
        failures.append(
            PaperRunFailure(
                stage="broker_reconciliation",
                reason="open_orders_lingering",
                details={"open_order_count": len(open_orders)},
            )
        )
    report = build_paper_run_report(
        session_date=manifest.session_date if manifest is not None else datetime.now().date(),
        dry_run=bool(manifest.dry_run) if manifest is not None else False,
        stage="ledger_summary",
        counts={"orders": len(orders), "open_orders": len(open_orders), "fill_count": len(fills)},
        failures=tuple(failures),
        meta={
            "run": _json_safe(run) if run is not None else None,
            "manifest": _json_safe(manifest) if manifest is not None else None,
        },
        run_id=run_id,
    )
    alerts = build_operator_alerts(report=report, state_payload=state_payload)
    return {
        "command": command,
        "ledger_path": str(ledger_path),
        "run_id": run_id,
        "run": _json_safe(run) if run is not None else None,
        "manifest": _json_safe(manifest) if manifest is not None else None,
        "report": report.to_dict(),
        "orders": [_json_safe(order) for order in orders],
        "open_orders": [_json_safe(order) for order in open_orders],
        "fills": [_json_safe(fill) for fill in fills],
        "alerts": [alert.to_dict() for alert in alerts],
        "latest_state": _json_safe(state_payload) if state_payload else None,
    }


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        payload = {
            key: _json_safe(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
        return payload
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _latest_state_payload(strategy_id: str) -> dict[str, Any]:
    healthcheck = build_paper_daily_healthcheck(strategy_id)
    return dict(healthcheck.latest_state or {})


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = dispatch_command(args)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

