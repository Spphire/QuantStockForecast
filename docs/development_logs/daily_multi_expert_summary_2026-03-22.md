# Daily Multi-Expert Summary (2026-03-22)

## Focus

Today's work focused on the `multi-expert` research line rather than the product-grade execution line. The goal was to turn the project into a shared `signal -> white_box_risk -> execution` framework that can host multiple model experts under one consistent interface.

## Completed

- Implemented and standardized the expert stack under `model_prediction` so that `lightgbm`, `xgboost`, `catboost`, `lstm`, and `transformer` all expose a compatible `train / predict` flow.
- Added the `ensemble` expert so multiple model outputs can be combined through the same registry and downstream signal interface.
- Registered `ensemble` in [expert_registry.py](C:/Users/Apricity/Desktop/股票/model_prediction/common/expert_registry.py) and completed smoke validation of the ensemble path.
- Completed the end-to-end experiment contract:
  - A-share training
  - U.S. zero-shot prediction
  - white-box risk
  - Alpaca-style historical execution replay
- Ran aligned comparison experiments on the shared U.S. evaluation window `2025-03-13` to `2025-12-23`.
- Updated the main experiment report and comparison table:
  - [us_a_share_multi_expert_report.md](C:/Users/Apricity/Desktop/股票/docs/experiments/us_a_share_multi_expert_report.md)
  - [aligned_expert_ensemble_comparison.csv](C:/Users/Apricity/Desktop/股票/docs/experiments/assets/us_a_share_multi_expert_report_assets/aligned_expert_ensemble_comparison.csv)

## Key Outcomes

- Single experts and the ensemble now all fit into the same downstream contract.
- The current best aligned single-expert execution result is `transformer`.
- The current best aligned ensemble execution result is `ensemble_mean_score`.
- The main bottleneck is no longer infrastructure. It is the gap between strong `signal / white_box_risk` performance and weaker `execution` performance after transaction costs, weight caps, and realistic order sizing constraints.

## Branching Note

- This branch is intended for `multi-expert` research and documentation work.
- Product-grade execution hardening should continue separately so the two lines do not interfere with each other.

## Recommended Next Steps

- Add a fixed external benchmark such as `SPY buy-and-hold` or a fixed equal-weight U.S. pool benchmark.
- Add ensemble weighting schemes beyond equal-weight aggregation.
- Separate research execution replay from product execution codepaths more explicitly in documentation and branch strategy.
