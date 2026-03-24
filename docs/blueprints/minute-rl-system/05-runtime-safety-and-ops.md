# 05 运行门禁与运维安全

## 1. 最低上线标准

1. 因果契约通过并可机器审计。
2. reward 归因可追溯且口径固定。
3. run lock、幂等控制、watchdog 全链路可用。
4. 模拟器校准通过。
5. 基线策略连续稳定运行并达标。

## 2. 三条红线

1. 发现时间泄露或错位，立即停机。
2. 执行质量触发 critical（拒单/挂单/回撤/幂等失效），立即降级。
3. 训练异常（NaN/Inf 或持续梯度异常），立即冻结 challenger。

## 3. SLO/SLA

1. `bar_lag_seconds`: p95 <= 90s，p99 <= 180s。
2. 决策延迟：p95 <= 5s，p99 <= 10s。
3. submit->accepted：p95 <= 2s，p99 <= 5s。
4. submit->terminal：p95 <= 180s，p99 <= 300s。
5. `reject_rate <= 2%`（按日）。
6. 超时挂单占比 <= 3%（>5分钟仍 open）。
7. critical 告警 5 分钟内响应，warning 30 分钟内响应。

## 4. Fail-Fast（运行期）

1. `run_lock` 获取失败且发现重入。
2. 同 `decision_id` 重复下单尝试。
3. 数据截止时间晚于决策时间。
4. `open_order_age_max_seconds > 300` 且 watchdog 处理失败。
5. `reject_rate_t > 0.10`。
6. 账户非 active 或被交易封锁。
7. 任意连续 `5` 个 slot 内 `reject_rate >= 10%` 或 `slippage_bps` 高于当周基线中位数 `+5bps`。
8. 时钟偏差超阈值：`|local_clock - broker_clock| > 500ms` 或 `|broker_clock - market_clock| > 500ms`。

## 5. 动作生效率监控

1. `action_raw_vs_executed_gap` 必须持续监控。
2. `constraint_binding_rate_by_dimension` 必须持续监控。
3. 门槛要求：
   - `mean(action_raw_vs_executed_gap) <= 0.08`
   - `p95(action_raw_vs_executed_gap) <= 0.15`
4. 若某维 `constraint_binding_rate_by_dimension > 70%` 且连续 `3` 个有效交易日成立，该维必须从 RL 动作空间摘除或冻结。
5. 若 `clip_ratio > 0.50` 连续 `20` 个 slot，立即触发 fail-fast（冻结 challenger + 停止在线训练 + 降级基线）。
6. 若单 slot `action_raw_vs_executed_gap > 0.15`，该 slot 及对应 `30min` 延迟奖励样本只允许进入 stress buffer，禁止写入主 replay。

## 6. 运行与训练职责分离

1. 训练不阻塞执行。
2. 执行进程负责订单生命周期闭环。
3. trainer 只读审计事件流，不直接读 broker 实时 API。
