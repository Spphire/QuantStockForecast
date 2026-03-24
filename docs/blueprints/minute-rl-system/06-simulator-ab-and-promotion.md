# 06 模拟器、A/B 与晋级规则

## 1. 模拟器规则（必须写死）

1. `submit_latency_ms`
2. `ack_latency_ms`
3. `fill_rule = next_bar_open_rule`（首版固定，禁止 same-bar 成交）
4. `cancel_effective_latency_ms`
5. `max_fill_fraction_per_bar`
6. partial fill 与 stale order 定义
7. `VWAP` 仅允许作为 `t+1` bar 内价格代理，不得替代成交时点规则。

## 2. 模拟器校准阈值

按周对比真实 paper：

1. `abs(fill_rate_sim - fill_rate_real) <= 0.10`
2. `abs(reject_rate_sim - reject_rate_real) <= 0.03`
3. `abs(slippage_bps_sim - slippage_bps_real) <= 5 bps`
4. `abs(stale_open_ratio_sim - stale_open_ratio_real) <= 0.05`
5. `open_order_duration_p95_sim / open_order_duration_p95_real in [0.8, 1.25]`
6. 校准结论必须绑定 `universe_version + trading_regime + execution_mode`，三者任一不匹配视为未校准。
7. 样本下限：`effective_paper_days >= 5`、`terminal_order_count >= 300`、`symbols_covered >= 30`。

校准超阈值时执行 fail-close：

1. 禁止该模拟器产物进入晋级评审。
2. 连续两周失败则暂停 IQL 新版本晋级。
3. 校准范围不匹配（universe/regime/execution_mode）同样执行 fail-close。

## 3. A/B 实验协议

1. A 组：`Bandit + white-box`。
2. B 组：`IQL + SAC` challenger。
3. 两组必须共享：
   - 同 reference clock
   - 同 symbol universe 快照
   - 同触发时刻规则
4. 三层对照：
   - 理论 target 对照
   - broker ack/fill 对照
   - PnL 与执行质量对照

## 4. Champion / Challenger 晋级门槛

1. 前置门禁：最近一轮模拟器校准必须通过，否则 challenger 不得进入晋级评审。
2. Shadow 阶段 >= 10 个完整有效交易日。
3. 小资金实单阶段 >= 10 个完整有效交易日。
4. 仅 `invalid_slot_ratio <= 5%` 的交易日可计入评审窗口。
4.1 `effective_day` 定义（冻结）：
   - `slot_coverage >= 95%`
   - `invalid_slot_ratio <= 5%`
   - 无执行 critical
   - `dry_run_only_slot_ratio <= 10%`
4.2 paired 评审规则（冻结）：
   - A/B 两组必须使用共同 `effective_day` 集合
   - 缺失配对日不得进入 bootstrap 统计
5. 必须同时满足：
   - `mean_daily_excess_return > 0`
   - `median_daily_excess_return >= 0`
   - `max_drawdown` 不劣化超过 20%
   - `turnover` 不高于基线 25%
   - `reject_rate_diff <= +1.0pp`（绝对百分点）
   - `slippage_bps_diff <= +3.0bps`
   - `fill_rate_diff_pp >= -10.0pp`
6. 统计门槛：
   - rolling-day block bootstrap 下 `P(challenger > baseline) >= 0.65`
   - `bootstrap_block_len = 5 trading days`
   - `bootstrap_resamples = 10000`
7. 自动降级触发：
   - 连续 `2` 个有效交易日满足：`mean_daily_excess_return < 0` 且（`reject_rate_diff > +1.0pp` 或 `slippage_bps_diff > +3.0bps`）
   - 执行 critical
   - 训练 fail-fast
