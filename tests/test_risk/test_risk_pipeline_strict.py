from __future__ import annotations

from pathlib import Path

import pandas as pd

from risk_management.white_box.protocols import strict_white_box_kwargs
from risk_management.white_box.risk_pipeline import run_white_box_risk


def _write_predictions_csv(tmp_path: Path, rows: list[dict[str, object]], name: str) -> Path:
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")
    return path


def test_run_white_box_risk_prefers_explicit_benchmark_symbol(tmp_path: Path) -> None:
    predictions_csv = _write_predictions_csv(
        tmp_path,
        [
            {"date": "2026-01-02", "symbol": "SPY", "pred_score": 0.10, "target_return_5d": 0.020},
            {"date": "2026-01-02", "symbol": "AAA", "pred_score": 0.90, "target_return_5d": 0.050},
            {"date": "2026-01-02", "symbol": "BBB", "pred_score": 0.80, "target_return_5d": -0.010},
        ],
        "benchmark_pref.csv",
    )
    result = run_white_box_risk(
        predictions_csv,
        output_dir=tmp_path / "benchmark_pref",
        top_k=2,
        rebalance_step=5,
        benchmark_symbol="SPY",
    )

    summary = result["summary"]
    assert abs(float(summary["benchmark_total_return"]) - 0.02) < 1e-9


def test_run_white_box_risk_sector_neutralization_changes_selection(tmp_path: Path) -> None:
    predictions_csv = _write_predictions_csv(
        tmp_path,
        [
            {
                "date": "2026-01-02",
                "symbol": "AAA",
                "pred_score": 0.95,
                "target_return_5d": 0.020,
                "industry_sector": "Tech",
            },
            {
                "date": "2026-01-02",
                "symbol": "BBB",
                "pred_score": 0.94,
                "target_return_5d": 0.010,
                "industry_sector": "Tech",
            },
            {
                "date": "2026-01-02",
                "symbol": "CCC",
                "pred_score": 0.83,
                "target_return_5d": 0.030,
                "industry_sector": "Health",
            },
            {
                "date": "2026-01-02",
                "symbol": "DDD",
                "pred_score": 0.80,
                "target_return_5d": -0.010,
                "industry_sector": "Health",
            },
        ],
        "sector_neutral.csv",
    )

    baseline = run_white_box_risk(
        predictions_csv,
        output_dir=tmp_path / "sector_baseline",
        top_k=2,
        rebalance_step=5,
    )
    neutralized = run_white_box_risk(
        predictions_csv,
        output_dir=tmp_path / "sector_neutralized",
        top_k=2,
        rebalance_step=5,
        sector_neutralization=True,
        sector_column="industry_sector",
    )

    baseline_positions = pd.read_csv(baseline["positions_path"], encoding="utf-8")
    neutralized_positions = pd.read_csv(neutralized["positions_path"], encoding="utf-8")

    assert set(baseline_positions["symbol"]) == {"AAA", "BBB"}
    assert set(neutralized_positions["symbol"]) == {"AAA", "CCC"}


def test_run_white_box_risk_strict_filters_apply_median_volume_and_vol_cap(tmp_path: Path) -> None:
    predictions_csv = _write_predictions_csv(
        tmp_path,
        [
            {
                "date": "2026-01-02",
                "symbol": "AAA",
                "pred_score": 0.90,
                "target_return_5d": 0.010,
                "close": 20.0,
                "median_dollar_volume_20": 60_000_000.0,
                "vol_20": 0.03,
                "industry_sector": "Tech",
            },
            {
                "date": "2026-01-02",
                "symbol": "BBB",
                "pred_score": 0.89,
                "target_return_5d": 0.010,
                "close": 20.0,
                "median_dollar_volume_20": 40_000_000.0,
                "vol_20": 0.03,
                "industry_sector": "Tech",
            },
            {
                "date": "2026-01-02",
                "symbol": "CCC",
                "pred_score": 0.88,
                "target_return_5d": 0.010,
                "close": 20.0,
                "median_dollar_volume_20": 60_000_000.0,
                "vol_20": 0.05,
                "industry_sector": "Health",
            },
            {
                "date": "2026-01-02",
                "symbol": "DDD",
                "pred_score": 0.87,
                "target_return_5d": 0.010,
                "close": 20.0,
                "median_dollar_volume_20": 60_000_000.0,
                "vol_20": 0.03,
                "industry_sector": "Health",
            },
        ],
        "strict_filters.csv",
    )

    result = run_white_box_risk(
        predictions_csv,
        output_dir=tmp_path / "strict_filters",
        **strict_white_box_kwargs(),
    )

    positions = pd.read_csv(result["positions_path"], encoding="utf-8")
    assert set(positions["symbol"]) == {"AAA", "DDD"}
