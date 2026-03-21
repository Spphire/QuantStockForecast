"""Persistent state and journal helpers for paper-trading runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def strategy_state_dir(strategy_id: str) -> Path:
    path = PROJECT_ROOT / "execution" / "state" / strategy_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_journal_row(path: Path, row: dict[str, Any]) -> None:
    frame = pd.DataFrame([row])
    if path.exists():
        existing = pd.read_csv(path, encoding="utf-8-sig")
        combined = pd.concat([existing, frame], ignore_index=True)
    else:
        combined = frame
    combined.to_csv(path, index=False, encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_latest_state(strategy_id: str, payload: dict[str, Any]) -> dict[str, str]:
    state_dir = strategy_state_dir(strategy_id)
    latest_state_path = state_dir / "latest_state.json"
    latest_state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    append_journal_row(state_dir / "run_journal.csv", payload)
    append_jsonl(state_dir / "run_journal.jsonl", payload)
    return {
        "state_dir": str(state_dir),
        "latest_state_path": str(latest_state_path),
        "run_journal_csv_path": str(state_dir / "run_journal.csv"),
        "run_journal_jsonl_path": str(state_dir / "run_journal.jsonl"),
    }


def write_order_journal(strategy_id: str, rows: list[dict[str, Any]]) -> str:
    state_dir = strategy_state_dir(strategy_id)
    journal_path = state_dir / "order_journal.csv"
    if rows:
        frame = pd.DataFrame(rows)
        if journal_path.exists():
            existing = pd.read_csv(journal_path, encoding="utf-8-sig")
            frame = pd.concat([existing, frame], ignore_index=True)
        frame.to_csv(journal_path, index=False, encoding="utf-8")
    elif not journal_path.exists():
        pd.DataFrame().to_csv(journal_path, index=False, encoding="utf-8")
    return str(journal_path)
