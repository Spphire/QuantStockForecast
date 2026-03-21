#!/usr/bin/env python3
"""Compatibility train entrypoint for the ensemble combiner.

The ensemble does not fit a separate statistical model. This entrypoint keeps
the same train/predict dispatch shape as the other experts, but it simply
reuses the prediction-time combination pipeline to validate the provided expert
outputs and persist the ensemble manifest.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from model_prediction.ensemble.scripts.predict_ensemble import main as predict_main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(predict_main())
