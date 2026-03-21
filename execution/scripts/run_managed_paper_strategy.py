#!/usr/bin/env python3
"""Thin wrapper for the managed paper runner."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from execution.managed.apps.run_multi_expert_paper import main


if __name__ == "__main__":
    raise SystemExit(main())

