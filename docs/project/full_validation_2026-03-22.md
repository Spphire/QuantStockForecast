# Full Validation Report 2026-03-22

## Scope

本次验证覆盖四层：

1. 自动化单元测试与运行时回归测试
2. 每个 expert 的训练与预测验证
3. multi-expert -> white-box risk -> managed execution 的 dry-run 全流程验证
4. 两套策略的 Alpaca paper 实盘提交流程验证

时间基准：

- 当前执行日期：2026-03-22
- 时区：Asia/Shanghai

## Code Changes Verified In This Report

本报告对应的代码验证了以下关键修复：

- `execution.managed.live.reconciler` 支持在当前提交流程中把新 broker 订单显式绑定到当前 `run_id/session_date`
- `execution.managed.apps.run_multi_expert_paper` 在提交后立即把 broker 返回的订单快照写回 ledger/reconciler
- `execution.managed.apps.run_multi_expert_paper` 现在会在写完最终 `run_summary.json` 后再同步 `execution/runtime/<strategy>/latest`
- `tests/test_apps/test_managed_submit.py`
- `tests/test_apps/test_reconciler.py`
- `tests/test_model_prediction/test_multi_expert_cli.py`

这次修复的直接目标是解决此前 `paper_ops latest-run/open-orders` 看不到最新 broker 订单的问题。

## Automated Tests

全量自动化测试命令：

```bash
python -m pytest
```

结果：

- `23 passed`

覆盖到的测试面包括：

- managed paper runtime / runner / submit / paper_daily / paper_ops / paper_smoke / reconciler
- multi-expert CLI synthetic training + prediction + ensemble
- strategy runtime

## Expert Training Validation

训练产物根目录：

- `artifacts/validation_runs/20260322/a_share_train`
- `artifacts/validation_runs/20260322/us_full_train`

### A-share trained experts

训练输入：

- `C:\Users\Apricity\Desktop\股票\data\interim\akshare\universes\large_cap_50_20200101_20241231_hfq_normalized.csv`

| Expert | Test Rows | MAE | RMSE | Directional Acc. | Correlation | Best |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| catboost | 11648 | 0.036893 | 0.060407 | 0.489097 | -0.070705 | iter=1 |
| lightgbm | 11072 | 0.036956 | 0.060739 | 0.496207 | 0.109933 | iter=33 |
| lstm | 11648 | 0.036557 | 0.060287 | 0.515453 | 0.082478 | epoch=3 |
| transformer | 11648 | 0.037254 | 0.060803 | 0.503005 | -0.013751 | n/a |
| xgboost | 11072 | 0.037122 | 0.060747 | 0.490968 | 0.108092 | iter=34 |

### US-full trained experts

训练输入：

- `C:\Users\Apricity\Desktop\股票\data\interim\stooq\universes\us_large_cap_30_20200101_20260320_hfq_normalized.csv`

| Expert | Test Rows | MAE | RMSE | Directional Acc. | Correlation | Best |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| catboost | 7020 | 0.030806 | 0.044775 | 0.551140 | 0.104345 | iter=23 |
| lightgbm | 6750 | 0.030123 | 0.043437 | 0.542074 | 0.071201 | iter=40 |
| lstm | 7020 | 0.030712 | 0.044563 | 0.550712 | 0.158010 | epoch=3 |
| transformer | 7020 | 0.031057 | 0.045041 | 0.534330 | 0.060352 | n/a |
| xgboost | 6750 | 0.030045 | 0.043462 | 0.548000 | 0.053181 | iter=16 |

## Ensemble And White-Box Risk Validation

集成预测产物：

- `artifacts/validation_runs/20260322/zero_shot_ensemble/predict_summary.json`
- `artifacts/validation_runs/20260322/us_full_ensemble/predict_summary.json`

预测汇总：

| Ensemble | Rows | Symbols | Date Min | Date Max |
| --- | ---: | ---: | --- | --- |
| zero_shot_ensemble | 16110 | 30 | 2024-01-30 | 2026-03-20 |
| us_full_ensemble | 16110 | 30 | 2024-01-30 | 2026-03-20 |

white-box risk 产物：

- `risk_management/white_box/runtime/us_zeroshot_a_share_multi_expert_daily/risk_summary.json`
- `risk_management/white_box/runtime/us_full_multi_expert_daily/risk_summary.json`

当前风险摘要：

| Strategy | Model Name | Total Return | Benchmark Return | Max Drawdown | Mean Turnover |
| --- | --- | ---: | ---: | ---: | ---: |
| us_zeroshot_a_share_multi_expert_daily | us_zeroshot_a_share_multi_daily | 14.631363 | 5.520597 | -0.594110 | 0.349611 |
| us_full_multi_expert_daily | us_full_multi_expert_daily | 0.339377 | 1.844719 | -0.499622 | 0.357635 |

## Managed Dry-Run Validation

命令：

```bash
python -m execution.managed.apps.paper_smoke execution/strategies/us_zeroshot_a_share_multi_expert_daily.json --allow-unhealthy --skip-session-guard --account-equity 100000
python -m execution.managed.apps.paper_smoke execution/strategies/us_full_multi_expert_daily.json --allow-unhealthy --skip-session-guard --account-equity 100000
```

结果：

| Strategy | Smoke Run ID | Session Date | Targets | Orders | Blocked | Result |
| --- | --- | --- | ---: | ---: | ---: | --- |
| us_zeroshot_a_share_multi_expert_daily | `0950f24cbc564376a643e76363ef8f4b` | 2026-03-20 | 6 | 3 | 0 | pass |
| us_full_multi_expert_daily | `0eaf1a82cb874924a1fefbf31cc68cef` | 2026-03-13 | 6 | 4 | 0 | pass |

说明：

- `paper_smoke` 在这一步使用了 `--allow-unhealthy`
- 原因不是执行链路失败，而是两套策略在真实 paper submit 后都存在未成交 open orders，healthcheck 会据此给出预期中的 warning

## Alpaca Paper Validation

### 1. A-share trained experts -> mixed expert -> paper submit

策略：

- `execution/strategies/us_zeroshot_a_share_multi_expert_daily.json`

最终采用的验证 run：

- run id: `0e785f56536a46929adb1295a063f36e`
- session date: `2026-03-20`
- runtime dir: `execution/runtime/us_zeroshot_a_share_multi_expert_daily/20260321T201612Z`

提交结果：

- `submitted_count = 3`
- `paper_ops latest-run` 看到 `orders = 3`, `open_orders = 3`
- broker 直连查询：`open_orders = 3`, `positions = 0`, `paper = True`

healthcheck：

- `lingering_open_orders`
- `stale_session_date`

解释：

- `lingering_open_orders` 说明订单已被 paper broker 接收但尚未成交
- `stale_session_date` 对应最新 session date 为 `2026-03-20`，当前日期为 `2026-03-22`，属于数据新鲜度提醒，不是 submit 失败

### 2. A-share + US-full data trained experts -> mixed expert -> paper submit

策略：

- `execution/strategies/us_full_multi_expert_daily.json`

最终采用的验证 run：

- run id: `97709e5ed9d04c0da9089251334e5d27`
- session date: `2026-03-13`
- runtime dir: `execution/runtime/us_full_multi_expert_daily/20260321T201510Z`

提交结果：

- `submitted_count = 4`
- `paper_ops latest-run` 看到 `orders = 4`, `open_orders = 4`
- broker 直连查询：`open_orders = 4`, `positions = 0`, `paper = True`

healthcheck：

- `lingering_open_orders`
- `stale_session_date`

解释：

- `lingering_open_orders` 同样表示 paper broker 已接单但未成交
- `stale_session_date` 对应最新 session date 为 `2026-03-13`，当前日期为 `2026-03-22`

## Final Conclusion

本次融合后的项目已经完成并验证了以下闭环：

1. 每个 expert 可独立训练并生成预测
2. multi-expert ensemble 可输出统一预测结果
3. white-box risk 可生成 execution 使用的标准化 `risk_positions.csv` / `risk_actions.csv`
4. managed execution dry-run 可稳定跑通
5. Alpaca paper submit 可真实下发交易指令
6. `paper_ops latest-run/open-orders` 现在能正确反映最新 run 的 broker 订单

仍然存在但属于预期范围内的告警：

- paper 订单在市场未成交前会保持 `accepted/open`
- session date 与当前日期存在滞后时，healthcheck 会给出 `stale_session_date`

这两类状态都不代表本次融合或执行链路失败。
