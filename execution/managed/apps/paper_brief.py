from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from execution.managed.monitoring.briefing import generate_operation_brief


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a visual paper-ops brief for scheduled runs.")
    parser.add_argument("strategy_configs", nargs="+", help="One or more execution strategy JSON configs.")
    parser.add_argument("--phase", choices=("research", "submit"), required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--status", choices=("success", "partial", "failed"), default="success")
    parser.add_argument("--note", action="append", default=[], help="Optional operator note to show in the brief.")
    parser.add_argument("--notify", action="store_true", help="Send the brief summary to configured notification targets.")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--output-format", choices=("json",), default="json")
    return parser


def dispatch_command(args: argparse.Namespace) -> dict[str, object]:
    return generate_operation_brief(
        strategy_configs=[Path(path) for path in args.strategy_configs],
        phase=args.phase,
        output_root=args.output_root or None,
        title=args.title,
        status=getattr(args, "status", "success"),
        notes=getattr(args, "note", []),
        notify=bool(getattr(args, "notify", False)),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = dispatch_command(args)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
