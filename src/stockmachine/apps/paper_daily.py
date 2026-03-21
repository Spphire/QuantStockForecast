from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from execution.common.strategy_runtime import default_ledger_path, load_strategy_config
from stockmachine.apps.run_multi_expert_paper import run_strategy
from stockmachine.monitoring.healthcheck import build_paper_daily_healthcheck


DEFAULT_KILL_SWITCH_NAME = "paper_daily.kill"
NON_BLOCKING_HEALTHCHECK_REASONS = {
    "missing_latest_run",
    "missing_latest_manifest",
    "missing_latest_state",
}


@dataclass(slots=True, frozen=True)
class KillSwitchStatus:
    path: str
    active: bool
    reason: str
    payload: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "active": self.active,
            "reason": self.reason,
            "payload": self.payload,
        }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scheduler-friendly daily shell for managed paper execution.")
    parser.add_argument("strategy_config", help="Path to one execution strategy JSON config.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the managed paper workflow.")
    run_parser.add_argument("--session-date", default="")
    run_parser.add_argument("--submit", action="store_true")
    run_parser.add_argument("--account-equity", type=float, default=0.0)
    run_parser.add_argument("--current-positions-csv", default="")
    run_parser.add_argument("--output-dir", default="")
    run_parser.add_argument("--ledger-path", default="")
    run_parser.add_argument("--allow-unhealthy", action="store_true")
    run_parser.add_argument("--skip-session-guard", action="store_true")
    run_parser.add_argument("--require-paper", action="store_true")
    run_parser.add_argument("--kill-switch-path", default="")
    run_parser.add_argument("--output-format", choices=("json",), default="json")

    health_parser = subparsers.add_parser("healthcheck", help="Inspect the ledger health for this strategy.")
    health_parser.add_argument("--ledger-path", default="")
    health_parser.add_argument("--output-format", choices=("json",), default="json")
    return parser


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    strategy_config = load_strategy_config(args.strategy_config)
    strategy_id = str(strategy_config["strategy_id"])
    ledger_path = _resolved_ledger_path(strategy_id, getattr(args, "ledger_path", ""))
    kill_switch = read_kill_switch(strategy_id, getattr(args, "kill_switch_path", ""))
    healthcheck = build_paper_daily_healthcheck(strategy_id)

    blocking_reasons = [
        reason for reason in healthcheck.reasons if reason not in NON_BLOCKING_HEALTHCHECK_REASONS
    ]
    policy_allowed = not kill_switch.active and not blocking_reasons
    if not policy_allowed and not args.allow_unhealthy:
        return {
            "ok": False,
            "command": "run",
            "summary": {
                "strategy_id": strategy_id,
                "decision": "blocked_preflight",
                "policy_allowed": policy_allowed,
                "kill_switch_active": kill_switch.active,
                "healthcheck_reasons": list(healthcheck.reasons),
            },
            "preflight": {
                "kill_switch": kill_switch.to_dict(),
                "healthcheck": healthcheck.to_dict(),
            },
        }

    result = run_strategy(
        args.strategy_config,
        session_date_override=args.session_date,
        submit=args.submit,
        account_equity_override=args.account_equity,
        current_positions_csv=args.current_positions_csv,
        output_dir=args.output_dir,
        ledger_path=str(ledger_path),
        skip_session_guard=args.skip_session_guard,
        require_paper=args.require_paper,
    )
    return {
        "ok": True,
        "command": "run",
        "summary": result.summary,
        "report": result.report,
        "preflight": {
            "kill_switch": kill_switch.to_dict(),
            "healthcheck": healthcheck.to_dict(),
            "policy_allowed": policy_allowed,
            "override_used": bool(args.allow_unhealthy and not policy_allowed),
        },
    }


def healthcheck_command(args: argparse.Namespace) -> dict[str, Any]:
    strategy_config = load_strategy_config(args.strategy_config)
    strategy_id = str(strategy_config["strategy_id"])
    healthcheck = build_paper_daily_healthcheck(strategy_id)
    return {
        "ok": bool(healthcheck.healthy),
        "command": "healthcheck",
        "strategy_id": strategy_id,
        "healthcheck": healthcheck.to_dict(),
    }


def read_kill_switch(strategy_id: str, override: str = "") -> KillSwitchStatus:
    if override:
        path = Path(override)
    else:
        path = default_ledger_path(strategy_id).parent / DEFAULT_KILL_SWITCH_NAME
    if not path.exists():
        return KillSwitchStatus(path=str(path), active=False, reason="absent", payload=None)

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return KillSwitchStatus(path=str(path), active=True, reason="file_present", payload="")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = content
    if isinstance(payload, dict):
        active_value = payload.get("active")
        active = True if active_value is None else bool(active_value)
        reason = str(payload.get("reason") or payload.get("message") or "file_present")
        return KillSwitchStatus(path=str(path), active=active, reason=reason, payload=payload)
    normalized = str(payload).strip().lower()
    if normalized in {"0", "false", "off", "inactive", "clear", "none"}:
        return KillSwitchStatus(path=str(path), active=False, reason="explicitly_cleared", payload=payload)
    return KillSwitchStatus(path=str(path), active=True, reason=str(payload), payload=payload)


def _resolved_ledger_path(strategy_id: str, override: str = "") -> Path:
    return Path(override) if override else default_ledger_path(strategy_id)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        payload = run_command(args)
    else:
        payload = healthcheck_command(args)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
