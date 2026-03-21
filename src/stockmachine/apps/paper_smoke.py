from __future__ import annotations

import argparse
import json
from typing import Sequence

from stockmachine.apps import paper_daily


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a repeatable smoke harness for managed paper execution.")
    parser.add_argument("strategy_config", help="Path to one execution strategy JSON config.")
    parser.add_argument("--session-date", default="")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--account-equity", type=float, default=0.0)
    parser.add_argument("--current-positions-csv", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--ledger-path", default="")
    parser.add_argument("--allow-unhealthy", action="store_true")
    parser.add_argument("--skip-session-guard", action="store_true")
    parser.add_argument("--require-paper", action="store_true")
    parser.add_argument("--kill-switch-path", default="")
    return parser


def build_smoke_payload(args: argparse.Namespace) -> dict:
    run_args = argparse.Namespace(
        strategy_config=args.strategy_config,
        command="run",
        session_date=args.session_date,
        submit=args.submit,
        account_equity=args.account_equity,
        current_positions_csv=args.current_positions_csv,
        output_dir=args.output_dir,
        ledger_path=args.ledger_path,
        allow_unhealthy=args.allow_unhealthy,
        skip_session_guard=args.skip_session_guard,
        require_paper=args.require_paper,
        kill_switch_path=args.kill_switch_path,
        output_format="json",
    )
    run_payload = paper_daily.run_command(run_args)
    return {
        "command": "smoke",
        "ok": bool(run_payload.get("ok")),
        "run": run_payload,
        "recommended_commands": {
            "healthcheck": [
                "python",
                "-m",
                "stockmachine.apps.paper_daily",
                args.strategy_config,
                "healthcheck",
                "--ledger-path",
                args.ledger_path,
            ]
            if args.ledger_path
            else [
                "python",
                "-m",
                "stockmachine.apps.paper_daily",
                args.strategy_config,
                "healthcheck",
            ],
            "ops_latest_run": [
                "python",
                "-m",
                "stockmachine.apps.paper_ops",
                args.strategy_config,
                "latest-run",
                *(
                    ["--ledger-path", args.ledger_path]
                    if args.ledger_path
                    else []
                ),
            ],
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = build_smoke_payload(args)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
