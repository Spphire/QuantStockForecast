# 03 算法路线与动作设计

## 1. 算法决策

1. 主线：`IQL（离线预训练） + SAC（在线微调）`。
2. 安全基线：`Bandit + white-box`（用于降级和 A/B 对照）。
3. 保守备选：`CQL + SAC`（在 OOD 风险偏高时启用）。

## 2. 不建议首发

1. `TD3` 单独主线。
2. `PPO` 直接在线主力。
3. `Decision Transformer` 直接实盘主力。
4. RL 直接逐股逐单控制。

## 3. 动作空间（首版硬边界）

1. expert 权重动作：
   - 使用 `softmax` 投影到 simplex。
   - 单步变化约束：`||w_t - w_{t-1}||_1 <= 0.15`。
   - 单 expert 最大权重：`<= 0.50`。
2. 风控参数动作：
   - `max_gross_exposure` 单步变化 `<= 0.10`。
   - `max_turnover` 单步变化 `<= 0.10`。
   - `min_confidence` 单步变化 `<= 0.05`。
3. 执行强度动作：
   - 首版仅允许 3 档离散档位。

## 4. 分阶段解耦

1. M0/M1：仅学习 expert 权重。
2. M2：冻结权重，仅学习风险参数。
3. M3：引入执行强度控制并开启联合微调。

## 4.1 SAC 首发作用域（冻结）

1. 首发 `SAC` 仅作用于连续动作子空间：
   - expert 权重连续向量
   - 风控参数连续子集（按阶段放开）
2. 执行强度 3 档离散动作在首发阶段不纳入 SAC actor 输出，仍由白盒执行桥接规则控制。
3. 若后续要把离散执行强度纳入 RL，必须单独升级算法与契约版本，不得在同一评审窗口内切换。

## 5. OOD 风险控制

1. 冻结主指标：`state_md_score`（Mahalanobis distance of state embedding）。
2. 冻结副指标：`bc_action_nll`（behavior cloning action NLL）。
3. 冻结 scope：`scope_hash = universe_version + trading_regime + execution_mode + fill_rule_version + feature_schema_version`。
4. 冻结窗口与阈值：
   - 最近 `20` 个 slot，任一指标超过离线参考 `p99` 达 `3` 次记 `warning`
   - 达 `5` 次或连续 `2` 个有效交易日 `warning` 记 `freeze`
   - 连续 `2` 个有效交易日回到 `p95` 内才允许恢复
5. 在线阶段禁止重估 OOD 参考分布与阈值，只允许读取离线冻结参考桶。
6. `freeze` 触发后必须冻结在线更新并回退到最近稳定版本，promotion 评审直接阻断。
7. OOD 参考桶生成协议（v1）：
   - 仅由离线 clean 窗口生成
   - 每个 `scope_hash` 最少 `5000` transition
   - 固定 `embedding_model_version` 与 `bc_model_version`
   - 样本不足时直接 `fail-close`，不得降标准上线
