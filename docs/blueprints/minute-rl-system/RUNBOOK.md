# RUNBOOK

## 0. 总则

1. 适用范围：分钟级 RL 子系统全链路（数据、决策、执行、训练、晋级）。
2. 唯一真相源：ledger/event store。
3. 默认安全模式：`Bandit + white-box`，必要时 `dry-run only`。

## 1. 事故分组

1. 因果与时序：见 [08-extreme-scenarios-runbook.md](08-extreme-scenarios-runbook.md) 与 [09-data-and-clock-runbook.md](09-data-and-clock-runbook.md)。
2. 数据异常与时钟漂移：见 [09-data-and-clock-runbook.md](09-data-and-clock-runbook.md)。
3. 账本污染与幂等失效：见 [10-ledger-and-idempotency-runbook.md](10-ledger-and-idempotency-runbook.md)。
4. 配置漂移与人为误操作：见 [25-config-and-change-runbook.md](25-config-and-change-runbook.md)。
5. 模拟器与晋级评审：见 [06-simulator-ab-and-promotion.md](06-simulator-ab-and-promotion.md)。

## 2. 每个场景必须包含的字段模板

### 2.1 检测信号

1. `metric_name`
2. `threshold`
3. `window`
4. `trigger_rule`

### 2.2 自动动作

1. `mode_switch`
2. `training_freeze`
3. `order_policy`
4. `degrade_target`
5. `fail_fast`

### 2.3 人工介入条件

1. `must_page_operator`
2. `must_block_promotion`
3. `must_review_data`
4. `must_reconcile_account`

### 2.4 恢复标准

1. `stability_window`
2. `metric_recovery_threshold`
3. `reconcile_required`
4. `shadow_only_after_recovery`

### 2.5 审计输出

1. `incident_json`
2. `state_snapshot`
3. `order_snapshot`
4. `training_snapshot`
5. `promotion_impact_report`

## 3. 事故审计统一字段

1. `incident_id`
2. `category`
3. `strategy_id`
4. `account_id`
5. `slot_id`
6. `decision_id`
7. `execution_id`
8. `policy_model_version`
9. `config_digest`
10. `detected_at_utc`
11. `severity`
12. `affected_scope`
13. `auto_actions_taken`
14. `manual_actions_required`
15. `recovery_status`
