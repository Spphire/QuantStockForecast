#!/usr/bin/env python3
"""Dispatch a unified train/predict call to one model expert."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_prediction.common.expert_registry import available_experts, get_expert, resolve_script


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one model expert with a uniform train/predict entrypoint."
    )
    parser.add_argument("action", choices=["train", "predict"], help="Expert action to run.")
    parser.add_argument(
        "model",
        choices=available_experts(),
        help="Which expert module to dispatch to.",
    )
    parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the expert script. Prefix with -- if needed.",
    )
    return parser.parse_args()


def normalize_script_args(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def main() -> int:
    args = parse_args()
    expert = get_expert(args.model)
    script_path = resolve_script(args.model, args.action)
    if not script_path.exists():
        print(f"[ERROR] Expert script not found: {script_path}")
        return 1

    forwarded_args = normalize_script_args(list(args.script_args))
    command = [sys.executable, str(script_path), *forwarded_args]
    print(f"[INFO] Expert: {expert.name}")
    print(f"[INFO] Description: {expert.description}")
    print(f"[INFO] Script: {script_path}")
    result = subprocess.run(command, cwd=PROJECT_ROOT)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
