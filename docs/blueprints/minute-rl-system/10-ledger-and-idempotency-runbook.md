# 10 账本污染与幂等失效 Runbook

## 总原则

1. ledger/event store 是订单、成交、持仓、权益、reward 与训练样本的唯一真相源。
2. trainer 只允许读取审计后的 ledger/event store，不允许旁路读取 broker 作为训练标签。
3. execution-watchdog 是唯一允许写回 `order/fill/equity` 状态的进程。

## 场景 C1：账本污染

### 触发

1. 同 `order_id` 出现冲突状态且无法按时间解释。
2. 同 `fill_id` 重复且数量/价格冲突。
3. `equity_ledger` 与 `equity_broker` 偏差超过 `0.5%`。
4. 核心持仓权重偏差超过 `1%`。

### 自动处置

1. 冻结 challenger 在线训练与晋级评审。
2. 必要时切 `dry-run only`。
3. 执行 `ledger_consistency_scan` 与 `broker_vs_ledger_reconcile_snapshot`。
4. 污染 transitions 标记无效，不得进入训练。

### 恢复

1. `fill_id` 冲突数清零。
2. `order_id` 冲突数清零。
3. 权益偏差回到 `<= 0.1%`，核心权重偏差 `<= 0.25%`。
4. 恢复首日仅允许 shadow。

## 场景 C2：幂等失效

### 触发

1. 同唯一键 `(strategy_id, account_id, trading_day, slot_id, mode)` 出现多条最终动作。
2. 同 `decision_id` 触发多次真实提交。
3. 同 `execution_id` 映射多个 broker 订单。

### 自动处置

1. 停止新单提交。
2. 冻结在线训练。
3. 切保护模式：仅维护 open orders，不允许新开仓。
4. 标记 `idempotency_broken`。

### 恢复

1. 冲突 `decision_id/execution_id/唯一键` 全部清零。
2. 合法主记录明确，其余仅可废弃标记，不可覆盖删除。
3. 幂等检查连续 30 个 slot 通过。
4. 恢复首 30 个 slot 仅 shadow-only。

## 场景 C3：唯一真相源失守

### 触发

1. trainer 绕过 ledger 直接消费 broker 数据。
2. 非 watchdog 进程写入 order/fill/equity 状态。
3. reward builder 使用未审计旁路数据源。

### 自动处置

1. 停止在线训练与 replay 新写入。
2. challenger 仅 shadow-only；严重时 dry-run only。
3. 触发 `source_of_truth_audit` 路径扫描。

### 恢复

1. 训练与评审输入全部回归 ledger/event store。
2. 状态写路径收敛为唯一实现。
3. 污染 replay 重建或作废。
4. 连续 5 个训练窗口无 source-of-truth 告警后方可恢复。
