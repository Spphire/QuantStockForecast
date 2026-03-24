# 23 研究可追踪矩阵

更新时间：`2026-03-24`（`Asia/Shanghai`）

| 冻结决策 | 证据字段 | 审计脚本/SQL | 通过阈值 | 最小反例 | 防逃逸控制 |
| --- | --- | --- | --- | --- | --- |
| 因果时序链 | `feature_cutoff_ts/decision_ts/submit_ts/eligible_fill_start_ts/reward_close_ts/norm_asof_ts` | `causality_audit.py` + `causality_audit.sql` | `sample>=1000` 且 `violation=0`，并满足 `norm_asof_ts<=feature_cutoff_ts` | `submit_ts < decision_ts` 或 `norm_asof_ts > feature_cutoff_ts` | 分层抽样 + 必测 pre-open/open/close/stress |
| 三时钟一致性 | `clock_skew_local_broker_ms/clock_skew_broker_market_ms` | `check_clock_skew.py` | 偏差均 `<=500ms` | 开市前时钟漂移触发下单 | slot 级 `fail-close`，禁止下单 |
| fill rule 同构 | `fill_rule_version/first_fill_ts` | fill contract audit | 仅 `next_bar_open` 语义 | same-bar fill | `fill_contract_manifest.json` 单源配置 |
| reward 唯一归因 | `reward_leg_id/action_id/execution_id/fill_id/conflict_status` | `check_reward_attribution.py` | coverage `>=99.5%`，未解析 notional `<=0.1% equity` | 一笔 fill 映射多 action | 强制唯一约束 + 冲突仅入 stress |
| reward 主口径冻结 | `reward_window_type/reward_formula_version` | reward lint | 训练仅 `30min delayed` | 运行中切 `5min` 为主口径 | `reward_manifest.json` + evaluator 强校验 |
| replay 三桶治理 | `replay_bucket/sample_validity_flag/propagated_reward_window_end_ts` | replay lineage audit | 主桶 invalid 记录数 `=0` | slot 作废但30min延迟reward仍入主桶 | invalid 传播作业强制执行 |
| OOD 门禁 | `ood_ref_bucket_id/state_md_score/bc_action_nll/ood_status/ood_breach_count_20slot` | `ood_monitor.py` | 20-slot 内 3 次 warning，5 次或 2 日 freeze，2 日恢复 | 只监控单指标导致漏检 | 参考桶离线冻结，不允许在线重估 |
| scope_hash 一致性 | `scope_hash/calibration_scope_hash/ood_scope_hash/promotion_scope_hash` | `scope_hash_consistency_check.py` | 四类 scope hash 必须全一致 | 校准与晋级使用错域证据 | 统一 `scope_hash_builder.py`，CI 阻断不一致提交 |
| 校准作用域与TTL | `calibration_scope_hash/valid_until_day/effective_paper_days/terminal_order_count/symbols_covered` | `run_calibration_report.py` | scope匹配 + TTL有效 + `effective_paper_days>=5` + `terminal_order_count>=300` + `symbols_covered>=30` | 用过期或小样本校准推进晋级 | scope gate 前置阻断 |
| 晋级 paired 评审 | `effective_day_flag/bootstrap_block_len/bootstrap_resamples` | `evaluate_promotion.py` | paired effective-day + `P>=0.65` | 非paired拼窗口 | 参数写死 + 报告复现校验 |
| 证据边界 | `evidence_scope/environment_type/scope_disclaimer_present` | `report_linter.py` | 缺任一字段即 fail | paper 报告写成 live-ready | 文案 lint 阻断发布 |
| 整包回滚 | `stable_bundle_manifest_id/policy_model_version/feature_schema_version/reward_formula_version/action_bounds_digest/replay_shard_id` | `rollback_bundle_check.py` | 回滚必须整包一致 | 仅回滚模型不回滚数据/契约 | 强制 `stable_bundle_manifest` 校验与回滚 drill |
