# P0-FREEZE（午夜封版）

更新时间：`2026-03-23`（`Asia/Shanghai`）

本文件定义分钟级 RL 系统在进入实现与评审前必须冻结的 P0 规则。任一规则未满足时，只允许 `shadow` 或文档修订，不允许宣告可晋级。
若与其他章节阈值不一致，以本文件为准，其他文件必须同步更新。

## P0-001 因果时序冻结

- `rule_id`: `P0-001-causality-order`
- `rule`: `feature_cutoff_ts < decision_ts <= submit_ts < eligible_fill_start_ts <= reward_close_ts`，且 `eligible_fill_start_ts = next_bar_open_ts`。
- `trigger`: 任一 transition 违反时序，或 `state_t` 使用 `t+1` 信息。
- `auto_action`: 标记 `invalid_due_to_causality_violation`，停止 replay 写入，冻结 challenger。
- `evidence`: `feature_cutoff_ts`、`decision_ts`、`submit_ts`、`eligible_fill_start_ts`、`reward_close_ts`。

## P0-002 三时钟一致性冻结

- `rule_id`: `P0-002-clock-consistency`
- `rule`: 必须满足 `|local_clock - broker_clock| <= 500ms` 且 `|broker_clock - market_clock| <= 500ms`。
- `trigger`: 任意双时钟偏差超阈值。
- `auto_action`: 当前 slot `fail-close`，禁止下单，禁止写入主 replay。
- `evidence`: `local_clock_ts`、`broker_clock_ts`、`market_clock_ts`、`clock_skew_local_broker_ms`、`clock_skew_broker_market_ms`。

## P0-003 因果审计 Hard Gate

- `rule_id`: `P0-003-causality-audit-hard-gate`
- `rule`: 每次评审抽检 `>=1000` 条 transition，违规数必须 `= 0`。
- `trigger`: 未执行审计、抽检数不足、违规数大于 0。
- `auto_action`: 阻断训练、阻断晋级、阻断实单候选。
- `evidence`: `audit_sample_size`、`audit_violation_count`、`audit_run_id`。

## P0-004 Reward 归因冻结

- `rule_id`: `P0-004-reward-attribution-freeze`
- `rule`: reward 拆为即时执行项与延迟收益项；延迟项固定 `5min/30min`，主训练口径固定 `30min delayed reward`，并可追溯到 `action_id/reward_id`。
- `trigger`: reward 不可追溯，或运行中切换 reward 主口径。
- `auto_action`: 标记 `invalid_due_to_reward_attribution_drift`，停止在线训练，阻断晋级。
- `evidence`: `action_id`、`reward_id`、`reward_formula_version`、`reward_window_type`、`ledger_event_refs`。

## P0-005 动作空间冻结

- `rule_id`: `P0-005-action-space-freeze`
- `rule`: 权重投影到 simplex，`||w_t-w_{t-1}||_1<=0.15`，单 expert 权重 `<=0.50`；执行强度首版仅 3 档。
- `trigger`: 动作越界或加载未审批新维度/边界。
- `auto_action`: 拒绝加载配置，冻结 challenger。
- `evidence`: `action_space_version`、`action_before_projection`、`action_after_projection`、`action_bounds`。

## P0-006 生效率与样本污染冻结

- `rule_id`: `P0-006-action-effectiveness-replay-guard`
- `rule`: `mean(action_raw_vs_executed_gap)<=0.08` 且 `p95<=0.15`；若单 slot `gap > 0.15`，该 slot 及其 `30min` 奖励样本只进 `stress buffer`，禁止进主 replay。
- `trigger`: gap 超阈值，或存在超阈值样本进入主 replay。
- `auto_action`: 冻结该窗口训练样本并回退到上一稳定版。
- `evidence`: `action_raw_vs_executed_gap_mean`、`action_raw_vs_executed_gap_p95`、`replay_bucket`。

## P0-007 高 Binding 维摘除

- `rule_id`: `P0-007-binding-dimension-eject`
- `rule`: 任一动作维 `constraint_binding_rate_by_dimension > 70%` 且连续 `3` 个有效交易日成立，必须从 RL 动作空间摘除或冻结。
- `trigger`: 高 binding 连续超阈值。
- `auto_action`: 自动冻结该维并停止该维在线更新。
- `evidence`: `constraint_binding_rate_by_dimension`、`binding_days_count`。

## P0-008 幂等与唯一键冻结

- `rule_id`: `P0-008-unique-keys-and-idempotency`
- `rule`: 幂等键固定为 `(strategy_id, account_id, trading_day, slot_id, mode)`；同一 `decision_id` 只允许一组目标仓位；同一 `execution_id` 只允许一次真实提交。
- `trigger`: 唯一键冲突、重复提交、补跑覆盖历史。
- `auto_action`: 停止新单，切 `safe-hold`，冻结 replay。
- `evidence`: `idempotency_key`、`decision_id`、`execution_id`、`retry_run_id`、`conflict_count`。

## P0-009 唯一真相源冻结

- `rule_id`: `P0-009-single-source-of-truth`
- `rule`: `ledger/event store` 是训练与评审唯一真相源；trainer 禁止旁路读取 broker 作为训练标签；`execution-watchdog` 是唯一写入 `order/fill/equity` 的进程。
- `trigger`: 旁路读取、双写、读取未审计缓存。
- `auto_action`: 停止在线训练，标记 `invalid_due_to_source_of_truth_violation`，阻断晋级。
- `evidence`: `source_of_truth`、`writer_process_id`、`reader_process_id`、`ledger_event_ref`。

## P0-010 模拟器校准与适用域冻结

- `rule_id`: `P0-010-simulator-fail-close-scope`
- `rule`: 校准阈值固定：`abs(fill_rate_sim - fill_rate_real) <= 0.10`、`abs(reject_rate_sim - reject_rate_real) <= 0.03`、`abs(slippage_bps_sim - slippage_bps_real) <= 5bps`、`abs(stale_open_ratio_sim - stale_open_ratio_real) <= 0.05`；校准结论必须绑定 `universe_version + trading_regime + execution_mode`。
- `trigger`: 任一校准指标超阈值，或适用域不匹配。
- `auto_action`: fail-close，禁止该 simulator 结果进入晋级评审。
- `evidence`: `simulator_version`、`fill_rate_sim/real`、`reject_rate_sim/real`、`slippage_bps_sim/real`、`stale_open_ratio_sim/real`、`calibration_scope`。

## P0-011 晋级硬门槛与样本质量冻结

- `rule_id`: `P0-011-promotion-hard-gates`
- `rule`: 晋级前必须满足 `shadow>=10` 有效交易日、`small-capital>=10` 有效交易日、`P(challenger>baseline)>=0.65`、`reject_rate_diff<=+1.0pp`、`slippage_bps_diff<=+3.0bps`；仅 `invalid_slot_ratio<=5%` 的交易日可计入评审窗口。
- `trigger`: 任一门槛失败，或评审窗口含无效交易日。
- `auto_action`: 标记 `promotion_failed`，保留 baseline。
- `evidence`: `shadow_effective_days`、`small_capital_effective_days`、`bootstrap_probability`、`reject_rate_diff_pp`、`slippage_bps_diff`、`invalid_slot_ratio`。

## P0-012 盘中短窗硬停冻结

- `rule_id`: `P0-012-intraday-short-window-hard-stop`
- `rule`: 任意连续 `5` 个 slot 内，若 `reject_rate>=10%` 或 `slippage_bps` 高于当周基线中位数 `+5bps`，必须立即降级到 `Bandit + white-box`。
- `trigger`: 连续 5-slot 执行恶化超阈值。
- `auto_action`: 冻结 challenger、停止在线训练、停止新开仓。
- `evidence`: `rolling_5slot_reject_rate`、`rolling_5slot_slippage_bps`、`weekly_slippage_baseline_median`、`degrade_action_id`。
