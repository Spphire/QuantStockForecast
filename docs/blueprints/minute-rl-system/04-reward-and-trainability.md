# 04 奖励函数与可训练性

## 1. 奖励函数（分钟级）

```text
reward_t =
  w_ret  * z(excess_log_ret_t)
  - w_fee  * z(fee_cost_t)
  - w_slip * z(slippage_cost_t)
  - w_turn * z(turnover_excess_t)
  - w_dd   * z(drawdown_excess_t)
  - w_rej  * z(reject_rate_t)
  - w_open * z(stale_open_order_ratio_t)
  - w_jump * z(action_jump_t)

reward_t = clip(reward_t, -2.0, 2.0)
```

### 1.1 `reward_formula_version = v1`（冻结默认权重）

1. `w_ret = 1.00`
2. `w_fee = 0.35`
3. `w_slip = 0.35`
4. `w_turn = 0.20`
5. `w_dd = 0.30`
6. `w_rej = 0.30`
7. `w_open = 0.25`
8. `w_jump = 0.15`
9. 任何权重改动都必须升级 `reward_formula_version`，并切新评审窗口。

## 2. 奖励归因协议（硬约束）

1. 即时奖励只包含与当前 `action_id` 直接相关的执行项：
   - 新增手续费
   - 增量滑点
   - 新增拒单
   - 新增 stale open order
   - 动作抖动惩罚
2. 延迟收益奖励使用固定窗口回填：
   - `5min delayed excess reward`
   - `30min delayed excess reward`
3. 主训练口径固定使用 `30min delayed`，不可临时切换。
4. 每项奖励都必须可追溯到 `action_id`、`reward_id`、`reward_leg_id` 与原始事件字段。
5. 唯一归因链必须成立：`fill_id -> execution_id -> reward_leg_id -> action_id`。

## 3. 量纲与归一化

1. 收益项用 `EWMA z-score`。
2. 成本项统一转权益占比后归一化。
3. 风险项用预算归一化并截断。
4. 归一化参数按交易日重置并记录版本号。

## 4. 梯度回传结论

1. 可训练：actor/critic 网络内部可导，SAC 重参数化路径有效。
2. 不可导：成交撮合、拒单、白盒硬约束属于环境反馈，不做端到端求导。
3. 实施原则：训练图中避免硬离散算子（`argmax`/`round`/`hard top-k`）。

## 5. 训练健康检查（必须落盘）

1. `actor_grad_norm`
2. `critic_grad_norm`
3. `update_ratio`
4. `q_gap_mean/p95`
5. `reward_mean/std`
6. `entropy`
7. `nan_or_inf_count`

## 6. 训练 Fail-Fast

1. 参数或梯度出现 `NaN/Inf` 立即停止更新。
2. 相对最近 `5` 个 clean 窗口基线：
   - `actor_grad_norm` 或 `critic_grad_norm` 连续 `3` 次 `>5x` 或 `<0.2x` 立即回滚。
3. `update_ratio` 连续 `3` 次越界（`<1e-6` 或 `>1e-2`）立即回滚。
4. `q_gap_p95` 连续 `3` 个窗口 `>2x` 基线立即冻结 challenger。
5. `reward_std` 连续 `3` 个窗口 `<0.1x` 基线立即冻结 challenger。

## 7. 最小单测与 ablation

1. 单测：
   - 反传后参数变化
   - 极值稳定性
   - 奖励对齐
   - 泄露检测
   - 动作可导性
   - replay 有效性
2. ablation：
   - 去滑点惩罚
   - 去拒单惩罚
   - 去回撤惩罚
   - `SAC vs Bandit`
   - `IQL+SAC vs SAC(随机初始化)`
