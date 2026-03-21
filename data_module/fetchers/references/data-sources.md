# Stock Fetching Notes

## Goal

Pull raw stock data in a way that is easy to reproduce, inspect, and normalize later.

## Source Selection

Prefer sources that provide:

- stable field names
- explicit date coverage
- clear adjustment rules
- clear symbol identifiers
- predictable rate limits or export formats

## Raw File Rules

- Save untouched source files under `data/raw`.
- Include the provider name in the filename or parent directory.
- Do not rewrite raw files after normalization.

## Normalized File Rules

Map provider-specific headers into the shared project schema:

- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`

Keep optional fields when available:

- `symbol`
- `amount`
- `turnover`
- `provider`
- `adj_close`

## Handoff Rules

After fetching and normalization:

1. Save the normalized file to a staging area.
2. Record symbol coverage and date coverage.
3. Pass the staged file to cleaning before feature engineering.
