# 08 极端场景 Runbook

## 场景 A1：时间因果违规 / 泄露疑似

### 检测信号

1. 任一 transition 不满足：
   - `feature_cutoff_ts < decision_ts <= submit_ts < eligible_fill_start_ts <= reward_close_ts`
2. 发现 `feature_cutoff_ts >= decision_ts`。
3. 发现读取了 `t+1` 信息。
4. 泄露检测单测失败。

### 自动动作

1. challenger 标记为 `invalid_due_to_causality_violation`。
2. 立即停止在线训练与晋级评审。
3. 当前版本新增 replay 写入冻结。
4. 若已实单运行，立即降级到 `Bandit + white-box` 或 `dry-run only`。

### 人工介入条件

1. 任意一次真实因果违规必须人工介入。
2. 30 分钟内无法定位根因时，当日 challenger 禁止恢复。

### 恢复标准

1. 修复完成后重新跑泄露检测全量通过。
2. 抽检 `>=1000` 条 transition，违规 `=0`。
3. 使用新 `contract_version` 重新生成审计记录。
4. 恢复首日只允许 shadow。

## 场景 A2：执行层失控（拒单/挂单/幂等）

### 检测信号

1. `reject_rate_t > 0.10`。
2. `open_order_age_max_seconds > 300` 且 watchdog 未成功处理。
3. 同一 `decision_id` 重复提交。
4. `run_lock` 失效或 run overlap。
5. 账户状态非 active 或被封锁。

### 自动动作

1. 冻结 challenger 下单权限。
2. 停止在线训练。
3. 降级到 `Bandit + white-box`；幂等或账户异常时直接 `dry-run only`。
4. watchdog 强制处置 open orders（回查、撤单、风险收口）。

### 人工介入条件

1. 发生重复下单或幂等失效。
2. 账户状态异常。
3. 连续 2 个 slot 无法清理 stale orders。

### 恢复标准

1. stale open orders 清零或进入可解释终态。
2. 幂等与 run_lock 恢复。
3. 连续 30 个 slot 无重复下单和 critical 异常。
4. 恢复先 shadow，再小仓位。

## 场景 A3：训练层失稳（梯度/数值/reward）

### 检测信号

1. 参数或梯度出现 `NaN/Inf`。
2. `actor_grad_norm` 或 `critic_grad_norm` 连续 3 次异常。
3. `update_ratio` 连续 3 次越界。
4. `reward_std` 连续 3 个窗口塌陷。
5. `q_gap` 连续 3 次超阈值。

### 自动动作

1. 停止本轮训练并回滚到最近稳定版本。
2. challenger 标记为 `invalid_training_run`。
3. 当前训练窗口 replay 冻结，不参与晋级。

### 人工介入条件

1. 任意 `NaN/Inf`。
2. 连续两次训练窗口触发 fail-fast。
3. 怀疑 reward attribution 或 replay 污染。

### 恢复标准

1. 根因归类并修复完成。
2. 单 batch 前后向单测通过。
3. 极值稳定性单测通过。
4. 连续 5 个训练窗口梯度与 reward 指标恢复正常。
5. 恢复首阶段只允许 shadow。
