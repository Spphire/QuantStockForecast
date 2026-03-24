# 附录 D 阶段一交接包（2026-03-23）

时区：`Asia/Shanghai`

## 1. 红队交接（Bacon）

### 1.1 三个残余风险

1. `paper -> live` 执行偏差可能显著放大。
2. reward 归因在多订单/部分成交/延迟回填下可能错挂。
3. white-box 长期裁剪可能导致 RL 失去真实控制权。

### 1.2 最早预警信号

1. `fill_rate`、`slippage_bps`、`reject_rate` 持续偏离 paper/模拟器校准区间。
2. reward attribution coverage 下降，同一 `action_id` 对应异常多延迟事件，reward 分项与 ledger 对不上。
3. `action_raw_vs_executed_gap` 抬升，`constraint_binding_rate_by_dimension` 高位持续，`clip_ratio` 高频触发。

### 1.3 不建议重复讨论事项

1. 不再重复争论 `IQL/SAC/PPO/TD3` 主方向。
2. 不在本轮引入 `Decision Transformer` 或多智能体路线。
3. 不扩充花哨 reward，优先修实归因和审计闭环。

## 2. 蓝队交接（Arendt）

### 2.1 已冻结核心约束（不可轻易改）

1. `P0-001`：保守因果协议（`t` 决策，`t+1` 起可成交）。
2. `P0-003`：因果审计 `>=1000` 且 `0` 违规。
3. `P0-004`：reward 归因冻结（即时项 + 固定 `5min/30min`，主口径 `30min`）。
4. `P0-005`：动作空间边界与执行强度冻结。
5. `P0-007`：高 binding 维摘除门槛冻结（`>70%` 连续 `3` 天）。
6. `P0-008/P0-009`：幂等键和唯一真相源冻结（trainer 禁止旁路 broker）。
7. `P0-010`：模拟器校准 fail-close 阈值冻结。
8. `P0-011`：晋级门槛冻结（`shadow>=10`、`small-capital>=10`、`bootstrap>=0.65`、执行劣化门槛）。

### 2.2 第二阶段最值得深挖的空白

1. 将 `RUNBOOK` 统一为可执行值班手册。
2. 将 reward 归因落成字段级数据血缘图。
3. 将模拟器->paper 校准细化为可复现评审协议。

### 2.3 第二阶段最可能返工雷区

1. 为改阈值而改字段/主契约，导致审计链路分叉。
2. 未补齐校准与归因就提前推进 `IQL + SAC` 实装。
