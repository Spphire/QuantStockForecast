---
name: fetchers
description: Pull, normalize, and stage stock market datasets for downstream modeling, including OHLCV price history, index data, sector mappings, and other structured provider exports. Use when Codex needs to add or update stock data ingestion scripts, standardize raw provider columns into a common schema, or prepare fetched files for cleaning and feature engineering.
---

# Fetchers

## Overview

Use this skill to bring raw stock data into the project in a repeatable way. Keep raw files immutable, normalize them into a shared schema, and hand off clean staged files to downstream processing.

## Workflow

1. Choose the source and define the pull scope.
2. Save the untouched export under `data/raw`.
3. Normalize field names and basic types into a shared schema.
4. Record symbol, provider, and date coverage.
5. Pass the normalized file to cleaning and feature engineering.

Read [data-sources.md](references/data-sources.md) for guidance on choosing sources and file conventions.

## Shared Schema

Prefer these canonical columns after normalization:

- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`

Allow optional fields when available:

- `symbol`
- `amount`
- `turnover`
- `provider`
- `sector`
- `adj_close`

Use `scripts/normalize_ohlcv.py <input.csv> <output.csv>` to normalize common CSV header variants.

## Implementation Notes

Keep fetch logic and normalization logic separate. One script should focus on downloading or reading provider exports, and another should transform them into project-standard columns.

Do not overwrite raw provider files after the first successful fetch. Write new staged outputs into `data/interim` or another explicit staging area.

Always preserve enough metadata to answer:

- which source produced the file
- which symbols are covered
- which date range is covered
- whether prices are adjusted or unadjusted

When provider connectivity is unstable, prefer a documented fallback instead of failing the whole workflow. The current fetch scripts already fall back from Eastmoney to Sina through AKShare when needed.

## Resources

Use `scripts/normalize_ohlcv.py` for quick CSV normalization when provider headers differ.
Use `scripts/fetch_stock_history.py` to fetch raw history and emit a normalized file aligned with the LightGBM baseline.
Use `scripts/fetch_stock_universe.py` to build a merged multi-stock dataset for cross-sectional training.
Use `scripts/fetch_stock_metadata.py` to build industry metadata for neutralized backtests.

Read [data-sources.md](references/data-sources.md) before adding a new fetcher so the folder conventions stay consistent.

## Typical Requests

Use this skill for requests such as:

- "Add a fetcher for daily OHLCV data"
- "Normalize this provider CSV into the project schema"
- "Stage raw stock data for the cleaning pipeline"
- "Check what columns a new provider export should map to"
- "Build a multi-stock universe dataset for model training"

## Handoff

After normalization, route the staged file to the cleaning skill or folder before feature engineering.
