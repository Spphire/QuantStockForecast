# Strict Strategy Run (2026-03-22)

## Run Scope

This run follows peer-comparison strict setting and executes two strategies:

- `us_full_multi_expert_daily`
- `us_zeroshot_a_share_multi_daily`

Strict command template:

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py <predictions_csv> --metadata-csv data/interim/stooq/universes/us_large_cap_30_metadata.csv --strict-peer-comparison
```

## Output Artifacts

- `artifacts/peer_comparison_strict_20260322/summary_metrics.csv`
- `artifacts/peer_comparison_strict_20260322/run_report.md`
- `artifacts/peer_comparison_strict_20260322/us_full_multi_expert_daily/risk_summary.json`
- `artifacts/peer_comparison_strict_20260322/us_zeroshot_a_share_multi_daily/risk_summary.json`

##收益统计

| Strategy | Periods | Total Return | Benchmark Return (SPY) | Excess Return | Annualized Return | Max Drawdown | Win Rate | Mean Turnover |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `us_full_multi_expert_daily` | 41 | 21.67% | 14.99% | 6.68% | 27.26% | -5.97% | 56.10% | 0.4780 |
| `us_zeroshot_a_share_multi_daily` | 104 | 41.52% | 37.12% | 4.40% | 18.33% | -10.96% | 56.73% | 0.4212 |

## Notes

- `vol_20` and `median_dollar_volume_20` were added to strict run inputs by rolling
  computation from prediction source files before execution.
- Sector metadata comes from:
  `data/interim/stooq/universes/us_large_cap_30_metadata.csv`.
