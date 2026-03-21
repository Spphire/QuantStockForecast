---
name: lightgbm
description: Build, train, evaluate, and update LightGBM-based stock prediction workflows on structured market features such as OHLCV history, returns, rolling indicators, and other tabular factors. Use when Codex needs to create or refine a baseline stock model, validate a training dataset before modeling, define prediction targets, or compare LightGBM against other stock prediction methods.
---

# LightGBM

## Overview

Use this skill to implement a practical stock-prediction baseline with LightGBM. Favor it when the project is still centered on tabular features and needs a fast, strong baseline before moving to deeper sequence models.

## Workflow

1. Validate the dataset contract before training.
2. Define the prediction target and forecast horizon.
3. Split data strictly by time, never by random shuffle.
4. Train a LightGBM baseline for classification or regression.
5. Evaluate both model metrics and trading-oriented metrics.
6. Record feature definitions, label rules, and output paths.

Read [workflow.md](references/workflow.md) for the detailed checklist and common pitfalls.

## Dataset Contract

Expect the baseline dataset to be row-based and time ordered. Prefer these fields:

- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`

Allow optional metadata columns such as:

- `symbol`
- `amount`
- `turnover`
- `sector`
- engineered factors
- target columns such as `target_up_1d` or `target_return_5d`

Run `scripts/check_stock_dataset.py <csv-path>` before wiring training code when the schema is uncertain.

## Task Selection

Choose classification when the target is directional, such as "will the stock go up in 1 day".

Choose regression when the target is numeric, such as:

- next-day return
- next-5-day return
- next-window volatility

Prefer regression for cross-sectional stock selection, especially when the downstream step is "sort by predicted return and buy top-k names".

Keep the first implementation simple. Start with one target, one horizon, and one stable feature set.

## Implementation Notes

Prefer LightGBM as the first production-style baseline when:

- features are mostly structured
- training speed matters
- you want quick iteration on feature engineering

Do not leak future data into the training row. Rolling indicators, rankings, and market aggregates must be computed using only information available at that timestamp.

Evaluate more than accuracy. At minimum, capture:

- classification or regression loss metrics
- validation performance by time split
- strategy-level metrics such as hit rate, return, and drawdown when a backtest exists

## Resources

Use `scripts/check_stock_dataset.py` to validate a CSV dataset before model training.
Use `scripts/train_lightgbm.py` to prepare features or train a baseline model on the shared schema.
Use `scripts/backtest_topk.py` to backtest top-k selection directly from prediction outputs.
Use `scripts/backtest_topk.py` with metadata constraints when you need industry or liquidity neutralization at portfolio construction time.

Read [workflow.md](references/workflow.md) when defining targets, time splits, and evaluation rules.

## Typical Requests

Use this skill for requests such as:

- "Build a LightGBM baseline for stock涨跌预测"
- "Check whether this CSV can be used for LightGBM training"
- "Add a 5-day return target and retrain the baseline"
- "Compare the current LightGBM baseline against XGBoost"
- "Run a top-k backtest on the latest LightGBM prediction file"
- "Train a cross-sectional return model on a multi-stock universe"
- "Run an industry-neutral backtest on the current return model"
