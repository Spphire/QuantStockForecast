# 20 凌晨 02:00 冻结决策（最终收敛版）

更新时间：`2026-03-24`（`Asia/Shanghai`）

来源：`Godel` + `Bohr` 第五轮收敛裁决。

## 1. 到 02:00 必须冻结的关键决策（含先决条款）

0. 先决契约冻结：`state contract v1`、`offline dataset contract v1`、`transition/episode semantics v1`。
1. 冻结 `fill_rule_version`：仅 `next_bar_open_participation_v1`，禁止 same-bar fill。
2. 冻结 reward 主口径：主训练仅 `30min delayed reward`，`5min` 仅诊断。
3. 冻结 reward 唯一归因：`fill_id -> execution_id -> reward_leg_id -> action_id` 唯一映射。
4. 冻结 OOD 门禁：`state_md_score + bc_action_nll`，20-slot 内超过参考 `p99` 达 3 次 warning，达 5 次或连续 2 个有效日 warning 则 freeze，连续 2 个有效日回到 `p95` 内才恢复。
5. 冻结统一 `scope_hash`：`universe_version + trading_regime + execution_mode + fill_rule_version + feature_schema_version`。
6. 冻结 `effective_day` 定义与 paired bootstrap 口径（5-day block、10000 resamples）。
7. 冻结 replay 三桶：`main/stress/invalid`，invalid 强制传播到 `30min reward` 窗口。
8. 冻结降级恢复状态机：不得跳步恢复，同日二次触发锁到收盘。
9. 冻结稳定回滚为“整包回滚”：模型+特征+reward+动作边界+replay shard。
10. 冻结证据边界：paper 证据缺免责声明或错域，直接无效。

## 2. 本轮明确不做（防过载）

1. 不做盘口级微结构 simulator。
2. 不做在线自适应 OOD 阈值。
3. 不做联合动作全开在线优化。
4. 不做自动化连续效用函数替代硬门槛。
5. 不做 live 放量或越级 live-ready 结论。

## 3. 资源减半时的最小闭环（步骤 1-5）

1. 先冻结事件模型、因果门、三时钟门、幂等门。
2. 只跑 `Bandit + white-box` 分钟 runtime（不启在线 SAC）。
3. 完成 reward 归因与 replay 分桶，仅供离线训练。
4. 完成校准脚本、上线前检查单、报告 lint。
5. 跑 `shadow-only` 10 个有效交易日并生成研究用 go/no-go 包（不可用于 promotion/live candidate）。promotion 仍必须满足 `shadow>=10` 且 `small-capital>=10`。

## 4. 说明

1. `02:00` 前冻结的是“定义边界与验收标准”，不是要求所有代码在此刻完成。
2. 任何超出上述边界的扩展都进入后续迭代，不得挤占本轮主链路。
