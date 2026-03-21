"""Placeholder for future Alpaca trade-update streaming support."""

from __future__ import annotations


def stream_trade_updates_not_implemented() -> None:
    raise NotImplementedError(
        "Trade update streaming is not wired yet. Use REST snapshots plus saved execution logs for now."
    )
