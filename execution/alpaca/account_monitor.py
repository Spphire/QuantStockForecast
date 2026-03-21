"""Helpers for saving Alpaca account and position snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from execution.alpaca.client import AlpacaBroker


def save_account_snapshot(
    broker: AlpacaBroker, output_dir: str | Path, *, prefix: str = ""
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    account = broker.get_account_snapshot()
    positions = broker.list_positions()

    stem_prefix = f"{prefix}_" if prefix else ""
    account_path = output_path / f"{stem_prefix}account_snapshot.json"
    positions_path = output_path / f"{stem_prefix}positions_snapshot.json"

    account_path.write_text(json.dumps(account.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    positions_path.write_text(
        json.dumps([position.to_dict() for position in positions], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "account_path": str(account_path),
        "positions_path": str(positions_path),
    }
