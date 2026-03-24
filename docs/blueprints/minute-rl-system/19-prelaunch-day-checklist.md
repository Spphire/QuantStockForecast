# 19 上线前一日检查单（自动化优先）

更新时间：`2026-03-24`（`Asia/Shanghai`）

建议由 `minute_system/ops/scripts/prelaunch_checklist.py` 串联执行。任一项失败即 `BLOCK_LAUNCH=true`。

1. 运行因果审计：`sample_size>=1000` 且 `audit_violation_count=0`。
2. 三时钟检查：`|local-broker|<=500ms` 且 `|broker-market|<=500ms`。
3. 数据新鲜度：最近 10 个 slot `bar_lag_seconds p95<=90`，覆盖率 `>=99%`。
4. 数据完整性：无 schema 漂移、无非法值、无重复冲突 bar。
5. 唯一真相源边界：trainer 无 broker import；仅 watchdog 可写执行状态。
6. ledger 一致性：`fill_id/order_id` 冲突数为 `0`。
7. broker-vs-ledger 对账：权益偏差 `<=0.1%`，核心持仓权重偏差 `<=0.25%`。
8. 幂等与 run lock：重放同一 slot 不重复下单、不重复写最终动作。
9. reward 归因：`fill_id -> execution_id -> reward_leg_id -> action_id` 唯一映射，且 `coverage>=99.5%`、`unresolved_notional<=0.1% equity`。
10. action effectiveness：`mean gap<=0.08`、`p95<=0.15`，无坏样本混入主 replay。
11. 训练健康 smoke：无 `NaN/Inf`，梯度与更新比率在阈值内。
12. OOD 与状态机 drill：冻结/降级/冷却/恢复顺序正确，同日二次触发不自动恢复。
13. simulator 校准有效：核心指标在阈内，`scope + expiry` 仍有效，且 `effective_paper_days>=5`、`terminal_order_count>=300`、`symbols_covered>=30`。
14. 晋级评审脚本可复现：输出 `pass/fail/manual-review`，硬门槛失败必 `fail`。
15. paper/live 证据 lint：报告必须带 `evidence_scope` 与 `scope_disclaimer_present`，缺失即 fail。
16. `manual-review` 语义：在签字结论产生前，`BLOCK_LAUNCH=true`。
17. 训练样本门槛：`train_effective_days>=20`、`train_transitions>=5000`、主 replay 覆盖率达标，否则 `BLOCK_LAUNCH=true`。
