# LightGBM Stock Workflow

## Goal

Build a strong baseline stock model on structured features before adding more complex sequence models.

## Recommended Steps

1. Confirm the dataset uses time-ordered rows.
2. Decide on one target definition.
3. Build features from past data only.
4. Split train, validation, and test sets by time.
5. Train a small baseline first.
6. Compare feature importance and out-of-sample metrics.
7. Hand off predictions to a backtest if available.

Target options:

- binary direction
- multi-class direction
- next-window return

## Leakage Checks

- Do not use future close, future volume, or future ranks in the current row.
- Do not compute rolling features with centered windows.
- Do not random-shuffle time series before splitting.

## Minimum Metrics

For classification:

- accuracy
- precision
- recall
- F1
- AUC when probabilities are available

For regression:

- MAE
- RMSE
- rank correlation when relevant

For strategy validation:

- hit rate
- cumulative return
- max drawdown
- turnover when a trading rule exists

## Output Expectations

Record at least:

- input dataset path
- feature list
- target definition
- split boundaries
- model parameters
- evaluation summary
