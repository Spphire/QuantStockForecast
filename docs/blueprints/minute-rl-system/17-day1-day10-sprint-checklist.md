# 17 Day1-Day10 冲刺清单（可验收）

更新时间：`2026-03-24`（`Asia/Shanghai`）

## Day 1

1. 建立 `minute_system/` 目录骨架与 `schema.sql` 初版。
2. 冻结主键与唯一键：`slot/decision/execution/reward/transition`。
3. 建立 `configs/{runtime,ood_gate,promotion}.yaml` 与 `config_digest` 产物。
4. 冻结 `state contract v1`（见 `26-state-observation-contract.md`）。
5. 冻结 `offline dataset contract v1`（见 `27-offline-dataset-contract.md`）。
6. 冻结 `transition/episode semantics v1`（见 `28-transition-episode-semantics.md`）。

## Day 2

1. 落地 `state/models.py`、`state/ledger.py`，打通一条完整 transition 写入。
2. 落地 `runtime/run_lock.py`、`runtime/idempotency.py` 初版。
3. 验证重放同一 slot 不重复写入。

## Day 3

1. 落地 `runtime/clock_probe.py`、`runtime/slot_gate.py`。
2. 增加三时钟字段与 `>500ms` fail-close。
3. 完成 `sql/causality_audit.sql` 初版。

## Day 4

1. 落地 `runtime/execution_watchdog.py` 与 `decision->execution` 事件链。
2. 落地 `contracts/io_boundary.py` 与 `training/ledger_reader.py`。
3. 确认 trainer 不依赖 broker client。

## Day 5

1. 落地 `reward/attribution.py` 与 reward 归因 schema。
2. 落地 `reward/backfill.py`，支持 `5min/30min` 回填。
3. 验证 `fill_id -> execution_id -> reward_leg_id -> action_id` 唯一归因，且 `coverage>=99.5%`、`unresolved_notional<=0.1% equity`。

## Day 6

1. 落地 `runtime/action_projector.py`、`risk/white_box_bridge.py`。
2. 落地 `runtime/action_effectiveness.py`、`training/replay_router.py`。
3. 验证 `gap>0.15` 样本进入 `stress_buffer`。

## Day 7

1. 落地 `training/health_guard.py` 与训练 fail-fast。
2. 落地 `training/ood_monitor.py` 初版（双指标 + 连续窗口）。
3. 异常注入测试：`NaN/Inf`、梯度爆炸、OOD 连续超阈。

## Day 8

1. 落地 `ops/state_machine.py`、`ops/recovery_controller.py`。
2. 落地 `ops/scripts/run_state_machine_drill.py`。
3. 验证同日二次触发不会自动恢复 challenger。

## Day 9

1. 落地 `simulator/fill_contract.py`（next-bar 同构）。
2. 落地 `simulator/calibrate.py`、`simulator/scope_registry.py`。
3. 产出 sim-vs-paper 校准报告（含 scope + expiry）。

## Day 10

1. 落地 `ops/promotion/evaluate_promotion.py`。
2. 落地 `ops/report_linter.py` 与 paper scope 检查。
3. 跑三大回归套件并输出 `pass/fail/manual-review` 报告。
