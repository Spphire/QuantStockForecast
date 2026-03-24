# 18 隐藏耦合与失败模式审计

更新时间：`2026-03-24`（`Asia/Shanghai`）

来源：`Godel`（研究侧）+ `Bohr`（工程侧）第四轮深挖。

## 1. 研究侧隐藏耦合与断耦措施

1. `fill_rule_version` 与因果时序、reward闭窗、校准可比性强耦合。
断耦：统一 `fill_contract_manifest.json`，下游只读该 manifest。

2. `reward_formula_version`、`reward_leg_id`、`norm_asof_ts` 强耦合。
断耦：统一 `reward_manifest.json`，禁止混 manifest 评审。

3. `slot_id/decision_id/execution_id/retry_seq` 是统一身份契约。
断耦：只允许 `ids_contract.py` 生成 ID，业务代码禁止拼接。

4. `scope_hash` 同时约束校准、OOD、晋级。
断耦：统一 `scope_hash_builder.py`，所有评审脚本只认 hash。

5. `invalid_slot_ratio` 与 `30min delayed reward` 传播强耦合。
断耦：`invalid_propagation_job.py` 强制传播至窗口末端。

6. `action_bounds_digest` 与 gap/binding/OOD 基线耦合。
断耦：digest 变化必须切新评审窗口，禁止拼接旧新样本。

7. 三时钟与开市判断、跨日幂等耦合。
断耦：每 slot 固化单一 `clock_snapshot`，所有门禁统一消费。

8. `last_stable_model_version` 实为“稳定包指针”。
断耦：`stable_bundle_manifest.json` 整包回滚，禁止单项回滚。

## 2. 工程侧失败模式与防爆栅栏

1. 因果时序违规。
栅栏：`causality_audit.py + causality_audit.sql` 阻断训练/晋级。

2. 数据不新鲜/断档/schema漂移。
栅栏：`check_market_batch.py`，失败即 `skip-trading`/`dry-run only`。

3. 三时钟漂移或开市状态误判。
栅栏：`check_clock_skew.py + check_market_open_guard.py`。

4. 幂等失效与 run overlap。
栅栏：`run_lock.py + idempotency.py + replay_duplicate_slot.py`。

5. 唯一真相源失守与账本污染。
栅栏：`check_training_io_boundary.py + ledger_consistency_scan.py`。

6. reward 归因漂移或 replay 污染。
栅栏：`backfill_delayed_reward.py + check_reward_attribution.py`。

7. 动作生效率恶化与过强绑定。
栅栏：`check_action_effectiveness.py` + 自动摘维/分桶。

8. OOD/训练失稳叠加恢复振荡。
栅栏：`run_training_smoke.py + run_state_machine_drill.py`。

## 3. 研究侧红线（不可突破）

1. 不允许 same-bar fill 进入训练/校准/晋级。
2. 不允许在同窗口混用不同 reward/action/feature 契约。
3. 不允许在线重估 OOD 参考桶。
4. invalid slot 必须连带作废其 `30min delayed reward`。
5. 不允许结果出来后再改评审口径或 bootstrap 参数。
