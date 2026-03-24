# 24 工程可追踪矩阵

更新时间：`2026-03-24`（`Asia/Shanghai`）

| ID | 冻结决策 | Owner | 代码模块 | CI检查 | 运行门禁 | 回滚动作 |
| --- | --- | --- | --- | --- | --- | --- |
| `F01` | 分钟级事件模型冻结 | SA-RiskExec | `state/schema.sql`, `state/models.py`, `state/ledger.py` | `test_minute_ledger_schema.py` | schema/version 不匹配拒绝启动 | 冻结 replay 新写入，切 shadow-only |
| `F02` | 因果+三时钟冻结 | SA-Data + SA-RiskExec | `runtime/clock_probe.py`, `runtime/slot_gate.py`, `ops/audits/causality_audit.py` | `test_clock_gate.py`, `test_causality_audit.py`（含 `norm_asof_ts<=feature_cutoff_ts`） | 时序/时钟或 `norm_asof` 失败即 fail-close | 标记 invalid，降级基线 |
| `F03` | fill rule 同构冻结 | SA-RiskExec | `simulator/fill_contract.py`, `runtime/execution_watchdog.py` | `test_fill_contract.py` | fill contract 不一致拒绝加载 | 当前challenger失效，禁入晋级 |
| `F04` | 单写边界冻结 | SA-RiskExec | `contracts/io_boundary.py`, `runtime/execution_watchdog.py`, `training/ledger_reader.py` | `test_io_boundary.py` | 旁路读写即阻断训练 | 切 shadow-only，污染样本隔离 |
| `F05` | 幂等与run lock冻结 | SA-RiskExec | `runtime/run_lock.py`, `runtime/idempotency.py`, `runtime/decision_engine.py` | `test_idempotency_guard.py`, `replay_duplicate_slot.py` | 重复键/重入立即停新单 | safe-hold + 冻结在线训练 |
| `F06` | reward归因冻结 | SA-RL | `reward/attribution.py`, `reward/backfill.py`, `training/replay_router.py` | `test_reward_attribution.py` | 归因冲突/窗口漂移阻断训练 | 标记 drift 并隔离窗口 |
| `F07` | 动作契约冻结 | SA-RiskExec + SA-RL | `runtime/action_projector.py`, `contracts/action_envelope.py`, `risk/white_box_bridge.py` | `test_action_projection.py` | 动作越界/新维度拒绝加载 | 回退稳定版 |
| `F08` | replay分桶冻结 | SA-RL | `training/replay_router.py`, `runtime/action_effectiveness.py`, `training/invalid_propagation.py` | `test_action_effectiveness.py`, `test_invalid_propagation.py` | `gap>0.15` 等条件强制分桶并传播 invalid 到 30min 窗口 | 冻结当前训练窗口 |
| `F09` | OOD+恢复状态机冻结 | SA-RL + SA-Ops | `training/ood_monitor.py`, `ops/state_machine.py`, `ops/recovery_controller.py` | `test_ood_gate_and_state_machine.py`, `run_state_machine_drill.py` | OOD/失稳触发降级状态机 | 冻结challenger并回滚稳定包 |
| `F10` | 晋级与证据边界冻结 | SA-Ops | `ops/promotion/evaluate_promotion.py`, `ops/report_linter.py`, `simulator/calibrate.py` | `test_promotion_gate.py`, `test_simulator_calibration.py` | 门槛失败、证据越界或校准样本不足（`effective_paper_days<5`/`terminal_order_count<300`/`symbols_covered<30`）即阻断晋级 | `promotion_failed`，保留baseline |
| `F11` | scope_hash 一致性冻结 | SA-Ops + SA-RL | `contracts/scope_hash_builder.py`, `ops/scope_hash_consistency_check.py` | `test_scope_hash_consistency.py` | 校准/OOD/晋级 scope hash 不一致则阻断评审 | fail-close 并要求重建评审窗口 |
| `F12` | 稳定包整包回滚冻结 | SA-Ops + SA-RiskExec | `ops/stable_bundle_manifest.py`, `ops/rollback_controller.py` | `test_stable_bundle_rollback.py`, `run_rollback_drill.py` | 回滚请求若非整包一致直接拒绝 | 回退到最近合法 `stable_bundle_manifest` |
