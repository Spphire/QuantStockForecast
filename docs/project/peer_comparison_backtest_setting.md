# Peer Comparison Backtest Setting (QSF)

This document mirrors the strict peer-comparison setting currently used to
align with `StockMachine-20260321` P0 strict mode.

Code anchor:

- `risk_management/white_box/protocols.py`

## Strict Protocol Snapshot

- mode: `P0 Strict`
- market: `US`
- frequency: `daily`
- benchmark: `SPY`
- prediction start: `2025-01-01`

Walk-forward:

- train window: `36 months`
- validation window: `6 months`
- test window: `6 months`
- roll frequency: `monthly`
- purge window: `6 sessions`
- embargo window: `1 session`

Portfolio:

- long-only
- `top_k = 10`
- equal-weight
- max `2` names per sector
- sector neutralization: enabled (`industry_sector`)

Liquidity and risk filters:

- `close >= 10`
- `median_dollar_volume_20 >= 50,000,000`
- `vol_20 <= 0.04`

Execution/backtest:

- horizon: `5 sessions`
- one-way cost: `10 bps`
- entry/exit assumption: market-on-open

## Reproduction Command

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py <predictions_csv> --metadata-csv <metadata_csv> --strict-peer-comparison
```

This switch applies the strict defaults in one shot, including benchmark symbol,
liquidity/volatility filters, sector cap, and sector neutralization.
