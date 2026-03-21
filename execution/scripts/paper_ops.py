#!/usr/bin/env python3
"""Thin wrapper for managed paper ledger inspection."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.append(str(SRC_ROOT))

from stockmachine.apps.paper_ops import main


if __name__ == "__main__":
    raise SystemExit(main())
