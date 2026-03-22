# Test Report - Strict Peer Comparison

## 1. Report Metadata

- project: `QuantStockForecast`
- generated_at: `2026-03-22 14:23:21 +08:00`
- branch: `codex/integrate-stable-ops-20260322`
- commit_under_test: `f69b356107eedffd5cb50b67bdf9bbb38cd6ee77`
- related change: `Add strict peer-comparison protocol and risk tests`

## 2. Test Objective

This round verifies the strict peer-comparison integration borrowed from
`StockMachine-20260321`, including:

- frozen strict protocol contract
- strict white-box risk behavior (`SPY` benchmark, sector-neutral score, liquidity/vol filters)
- regression safety for existing execution and model-prediction workflows

## 3. Scope

Modules covered:

- `risk_management/white_box/protocols.py`
- `risk_management/white_box/risk_pipeline.py`
- `risk_management/white_box/scripts/run_white_box_risk.py`
- `model_prediction/common/signal_interface.py`
- `tests/test_risk/test_protocols.py`
- `tests/test_risk/test_risk_pipeline_strict.py`

## 4. Executed Test Commands

### 4.1 Full Regression Suite

```powershell
python -m pytest
```

Result:

- collected: `30`
- passed: `30`
- failed: `0`
- duration: `20.63s`

### 4.2 Strict Risk Focus Tests

Included inside full suite and verified explicitly in this round:

- `tests/test_risk/test_protocols.py` -> protocol default contract checks
- `tests/test_risk/test_risk_pipeline_strict.py` -> strict runtime behavior checks

## 5. Key Assertions Verified

1. Strict protocol is frozen and testable (`P0 Strict`, `SPY`, horizon `5`, `top_k=10`,
   `min_close=10`, `min_median_dollar_volume_20=50,000,000`, `max_vol_20=0.04`, sector cap `2`).
2. `run_white_box_risk` now supports strict-specific controls:
   benchmark symbol override, sector neutralization, median dollar volume filter, and vol cap filter.
3. CLI supports one-shot strict mode:
   `--strict-peer-comparison`.
4. Existing execution and model pipelines did not regress (full suite remained green).

## 6. Outcome

- overall_status: `PASS`
- release_readiness_for_strict_protocol: `READY`

## 7. Known Gaps / Not in This Test Round

- No live Alpaca order submission was executed in this report.
- Strict filters that rely on metadata columns (`industry_sector`,
  `median_dollar_volume_20`, `vol_20`) require those fields to exist in upstream prediction data.

## 8. Reproduction

```powershell
python -m pytest
python risk_management/white_box/scripts/run_white_box_risk.py <predictions_csv> --metadata-csv <metadata_csv> --strict-peer-comparison
```
