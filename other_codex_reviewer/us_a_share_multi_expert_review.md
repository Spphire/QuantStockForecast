# U.S. Zero-Shot Multi-Expert Report Review

## Scope

This review is based on [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md) and focuses on experimental validity, benchmark design, cost interpretation, and conclusion strength.

## Findings

1. **P0: The benchmark is internal, not an external market benchmark.**
   The report explicitly states that the benchmark is an "internal same-window, same-pool benchmark" rather than `SPY` or another tradable market index. The white-box benchmark is computed as the mean forward return of the available pool on each rebalance date, and the execution layer reuses that same path. This makes the benchmark a relative reference inside the candidate pool, not an external yardstick for market outperformance. As a result, phrases like "trails the internal same-window benchmark" are valid, but they do not support a claim that the strategy underperforms or approaches the broader U.S. market.
   Evidence: [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L17), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L19), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L21).

2. **P0: The cross-domain transfer conclusion is stronger than the evidence supports.**
   The report concludes that the system can generate transferable signals from A-share-trained models into U.S. equities. However, the comparison is limited to a single aligned window, a fixed U.S. zero-shot universe, and an internal benchmark. There is no external market baseline, no U.S.-trained in-domain control, and no broader window stability analysis. Under these conditions, the report can support "observed cross-domain performance on this window," but not a robust claim that transferability has been established.
   Evidence: [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L7), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L110), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L113).

3. **P1: The aligned comparison window may be too narrow to support stable ranking claims.**
   The main cross-expert table is restricted to 2025-03-13 through 2025-12-23. The report does not explain why this window was chosen, whether it was pre-committed, or whether results are stable across other windows. Without multi-window sensitivity analysis, confidence intervals, or seed stability checks, the ranking between experts and ensembles may reflect this specific period rather than a durable model advantage.
   Evidence: [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L7), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L62), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L92).

4. **P1: Cost reporting is not yet sufficiently interpretable for audit-grade evaluation.**
   The setup specifies `transaction_cost_bps=10`, but the table reports `Tx Cost` values such as `8519.42` and `7435.86` without unit definition or decomposition. It is not clear whether these values are total bps, currency amounts, or a compounded cost proxy. Because the report does not separate gross return, net return, slippage, and fee components cleanly, the economic interpretation of the execution layer remains ambiguous.
   Evidence: [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L44), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L62), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L92).

5. **P2: The report is directionally useful, but the conclusion wording should be tightened.**
   The report does a good job of separating risk-layer results from execution-layer results and explicitly acknowledges that execution realism is the bottleneck. That said, the final takeaway still leans toward a stronger transferability claim than the evidence warrants. A more defensible wording would be that the system shows cross-domain signal behavior on one aligned window, while the execution layer and benchmark design are still too limited for a stronger claim.
   Evidence: [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L108), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L113), [us_a_share_multi_expert_report.md](E:/CodeX/StockMachine-260321/us_a_share_multi_expert_report.md#L114).

## Positive Aspects

- The report is unusually explicit about the benchmark definition and does not pretend it is `SPY`.
- It cleanly separates white-box risk-layer results from Alpaca-style execution results.
- It includes aligned artifacts and a shared settings section, which improves traceability.
- It acknowledges the need for a fixed external benchmark in future iterations.

## Overall Assessment

This is a useful internal research report, but it is not yet strong enough to support broad claims about market outperformance or established cross-domain transfer. The main limitations are benchmark construction, single-window alignment, and incomplete cost interpretability. The report would be materially stronger if it added a fixed external benchmark, multi-window robustness checks, and a clearer breakdown of execution costs.

## Response

This review is directionally fair, and I agree with the main concern that the report should be framed as an internal research result rather than a stronger transferability claim.

### What I Accept

1. The benchmark criticism is correct. The current benchmark is an internal same-window, same-pool reference line, not an external market index benchmark.
2. The transferability conclusion should be narrower. The evidence supports observed cross-domain signal behavior on one aligned U.S. window, not robust transferability.
3. The current aligned comparison is still a single-window result, so the ranking should not be presented as durable without additional window stability checks.
4. The transaction-cost presentation needed to be made more explicit.

### What I Want To Clarify

1. The report already disclosed that the benchmark is internal rather than `SPY`; the main issue is not hidden methodology, but conclusion strength.
2. The aligned window `2025-03-13` to `2025-12-23` was chosen because it is the common overlap across the five expert prediction outputs used in the ensemble comparison, not because it was selected for best performance.
3. The document is intended as a research report on the multi-expert zero-shot stack, not as a production execution claim or a market-outperformance paper.

### What I Changed

1. I updated the main report wording to frame it explicitly as an internal research note.
2. I added an explanation for why the aligned window was chosen.
3. I clarified that `Tx Cost` is reported in simulated account currency (`USD`) and explained how it is computed in the execution replay.
4. I added an explicit `Limitations` section and tightened the final takeaway language.

### Next Steps

1. Add a fixed external benchmark such as `SPY buy-and-hold` or a fixed equal-weight U.S. pool benchmark.
2. Add multi-window robustness analysis instead of relying on one aligned overlap window.
3. Add a cleaner cost decomposition so fee proxy, slippage proxy, and other execution penalties can be read separately.
4. Add an in-domain U.S.-trained control in the same headline comparison table.

### Bottom Line

I treat this review as useful and mostly correct. The main fix is not to dispute the criticism, but to narrow the claim scope, clarify the benchmark and cost semantics, and strengthen the next evaluation round.
