# 11 24:00 封版检查单

## 红队阻断检查

- [ ] 时间因果契约无歧义：`feature_cutoff_ts < decision_ts <= submit_ts < eligible_fill_start_ts <= reward_close_ts`，且若存在 `first_fill_ts`，则 `first_fill_ts >= eligible_fill_start_ts`。
- [ ] 因果审计 hard gate：抽检 `>=1000` 条 transition，`0` 违规。
- [ ] reward 归因协议写死，主训练口径固定 `30min delayed`。
- [ ] `action_raw_vs_executed_gap`、`constraint_binding_rate`、`clip_ratio` 均为门槛，不只是监控。
- [ ] 动作空间边界和高 binding 摘维规则已量化。
- [ ] trainer 只读 ledger/event store，单写路径明确。
- [ ] 模拟器校准阈值与 fail-close 生效。
- [ ] shadow/实单/bootstrap/reject/slippage 晋级门槛量化完成。
- [ ] runbook 覆盖完成：`08`（极端场景）`09`（数据与时钟）`10`（账本与幂等）`14`（开盘前30分钟）。
- [ ] 阶段许可口径明确区分（M0/M1 vs 实单晋级准备）。

## 蓝队交付检查

- [ ] 多文件蓝图索引可读。
- [ ] 关键章节与附录链接有效。
- [ ] RUNBOOK 总入口可用。
- [ ] 版本字段与唯一键定义完整。
- [ ] 监督日志已落盘并可追溯。
