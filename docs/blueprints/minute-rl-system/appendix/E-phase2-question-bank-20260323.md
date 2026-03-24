# 附录 E 第二阶段质询清单（2026-03-23）

时区：`Asia/Shanghai`

## 1. 红队刁钻问题（Bacon）

1. 如何证明 `IQL -> SAC` 在线阶段未离开离线支持域？给 OOD 指标、阈值、连续超阈值冻结规则。
2. `action_raw_vs_executed_gap` 长期偏高时，如何区分 white-box 过强、actor 无效、执行层故障？给区分指标和处置顺序。
3. 为何主口径固定 `30min delayed reward`？给不选 `15min/60min` 的证据标准。
4. 部分成交与多分钟回填下，reward 如何唯一映射到 `action_id`？冲突时唯一决策原则是什么？
5. 模拟器校准通过后为何可外推 live？校准有效期、适用域、失效条件是什么？
6. paper/live 在 `fill_rate`、`slippage`、`reject_rate` 仅一项恶化时，何时继续、何时 fail-close？
7. 如何保证 trainer 永不旁路 ledger/event store？代码或流程级硬隔离是什么？
8. challenger 收益更优但执行质量略劣时，晋级裁决公式是什么？给硬门槛。
9. 如何避免降级后“恢复-再触发”振荡？给冷却时间、恢复顺序、同日二次触发规则。
10. 哪些裁决点必须人工签字？自动裁决与人工批准边界如何审计落盘？

## 2. 蓝队工程验收问题（Arendt）

1. `transition` 是否落盘了 `feature_cutoff_ts/decision_ts/submit_ts/eligible_fill_start_ts/reward_close_ts`，并可 SQL 查因果违规？
2. `reward_attribution` 是否能将每个分项映射到 `action_id/reward_id/execution_id`？
3. 动作边界投影是否是硬约束，并有单元测试覆盖单步变化上限？
4. `action_raw_vs_executed_gap` 与 `constraint_binding_rate_by_dimension` 是否已接入 fail-fast？
5. `run_lock` 与幂等键在执行入口是否真实生效，可否复现实验验证“重复触发不重复下单”？
6. trainer 是否仅从 ledger/event store 读取训练样本，并禁止旁路 broker？
7. 模拟器校准脚本能否输出 `fill/reject/slippage/stale/p95_duration` 的 sim-vs-paper 对比？
8. 晋级评审脚本能否自动计算 `shadow有效天数`、`bootstrap概率`、`reject_rate_diff_pp`、`slippage_bps_diff` 并输出 `pass/fail`？
9. `RUNBOOK` 各场景是否都有实际自动动作或可执行脚本，而非纯文档？
10. 所有 paper 报告是否强制携带 `evidence_scope` 与 `paper disclaimer`，缺失是否自动判无效？
