# 16 第二阶段共识执行计划（00:00-02:00 迭代版）

更新时间：`2026-03-24`（`Asia/Shanghai`）

来源：新专家 `Godel`（研究/RL）与 `Bohr`（工程/交付）第三轮交叉裁决。

## 1. Now（必须立刻推进）

1. 分钟级统一事件账本落地：`slot -> decision -> execution -> reward -> transition` 主链与唯一键。
2. 因果审计 Hard Gate 机器化：`sample_size>=1000` 且 `violation=0`，不满足直接阻断训练与晋级。
3. 三时钟采集与 slot fail-close：`|local-broker|<=500ms`、`|broker-market|<=500ms`。
4. `run_lock + idempotency`：同一 `(strategy_id,account_id,trading_day,slot_id,mode)` 只允许一组有效动作。
5. 唯一真相源与单写边界：trainer 只读 audited ledger，只有 watchdog 可写 `order/fill/equity`。
6. reward 唯一归因落表：引入 `reward_leg_id`，固定部分成交与延迟回填唯一映射。
7. replay 分桶治理：`main/stress/invalid` 三桶；invalid 必须传播到对应 `30min delayed reward` 窗口。
8. `fill_rule` 首版冻结为 `next_bar_open` 同构语义，禁止 same-bar fill。
9. OOD 门禁落地：双指标（`state_md_score` + `bc_action_nll`）+ 固定窗口（20 slot：3次 warning，5次或2个有效日 freeze，2个有效日恢复）。
10. 晋级评审与校准注册器：固定 scope hash、TTL、样本下限、paired bootstrap 与灰区裁决带。
11. 降级恢复状态机：冷却期、同日二次触发锁仓、恢复先 `shadow` 后 live。
12. 训练先决契约冻结：`state contract v1`、`offline dataset contract v1`、`transition/episode semantics v1`。
13. 主 replay 最低样本门槛冻结：`train_effective_days>=20`、`train_transitions>=5000`，不满足则禁止开训。

## 2. Next（紧随其后）

1. gap 分诊拆层：区分 white-box 裁剪、actor 漂移、执行层问题。
2. 训练健康相对基线阈值：`grad/q_gap/reward_std` 与 `last_stable_model_version` 回滚。
3. 盘前 T-30/T-15/T-5 Go/No-Go 快照量化。

## 3. Later（明确延期）

1. 自适应 OOD 阈值与在线动态重估。
2. 盘口级微结构 simulator 与复杂冲击建模。
3. 多维 regime-aware replay 精细分桶。
4. 自动化连续效用函数替代硬门槛评审。
5. 自动再晋级/多策略联动恢复。

## 4. Day1-Day10 冲刺节奏

1. `Day1-Day2`：建 `minute_system/` 骨架、schema、config digest、ledger 主链。
2. `Day3-Day4`：三时钟 gate、因果审计脚本、execution-watchdog 单写路径、I/O 边界。
3. `Day5-Day6`：reward 归因与回填、动作投影与 white-box 桥接、action effectiveness 分桶。
4. `Day7-Day8`：训练健康门、OOD 门禁、降级恢复状态机与 drill。
5. `Day9-Day10`：simulator fill contract + calibration registry、promotion evaluator、report linter、全套回归。

## 5. 三个关键回归套件

1. 因果与幂等套件：时序、三时钟、run lock、唯一键、单写者边界。
2. reward 与 replay 套件：唯一归因、`5min/30min` 回填、stress buffer 分流、防污染。
3. 运行降级与晋级证据套件：OOD freeze、恢复状态机、scope/TTL 校准、promotion gate、paper scope lint。

## 6. 执行边界

1. 不改 [P0-FREEZE.md](P0-FREEZE.md) 既有硬阈值和主契约。
2. 不把 paper 证据写成 live-ready 证据（必须保留 scope disclaimer）。
3. 两周内不做“好看但不可审计”的高级模型扩展。
