# 27 离线训练数据契约（Offline Dataset Contract v1）

更新时间：`2026-03-24`（`Asia/Shanghai`）

## 1. 目标

1. 固定 `IQL` 离线预训练数据来源、筛样规则与切分口径。
2. 保证离线数据可审计、可复现、可与后续在线评审配对。

## 2. 数据来源（唯一真相源）

1. 仅允许使用 `audited ledger/event store` 导出的 transition 数据。
2. 禁止使用 broker 原始实时接口直接构造训练标签。
3. 必须落盘以下来源版本：
   - `source_of_truth_version`
   - `feature_schema_version`
   - `reward_formula_version`
   - `fill_rule_version`
   - `scope_hash`

## 3. 可接受行为策略集合（behavior policies）

1. `Bandit + white-box` 基线版本（主集合）。
2. 审批通过的历史 challenger 版本（可选集合）。
3. 任一行为策略都必须有稳定版本号与运行期配置摘要（`config_digest`）。

## 4. 样本纳入与剔除

1. 纳入条件：
   - `sample_validity_flag=true`
   - `replay_bucket=main`
   - `scope_hash` 与当前训练目标一致
2. 剔除条件：
   - 因果违规、时钟违规、归因冲突、source-of-truth 违规
   - `gap>0.15` 及其传播到的 `30min` 延迟窗口样本
   - OOD 标记窗口内被冻结的样本

## 5. 切分规则（按交易日）

1. 固定按交易日切分，不允许随机打散：
   - `train: 70%`
   - `val: 15%`
   - `test: 15%`
2. 若用于 walk-forward 评审，必须在文档中单独声明窗口滚动规则。
3. 同一交易日不得同时出现在 train 与 val/test。

## 6. 最低样本门槛（开训前）

1. `train_effective_days >= 20`
2. `train_transitions >= 5000`
3. `main_replay_coverage >= 95%`
4. 每个关键 symbol 至少覆盖 `N_min` 有效 slot（由策略池配置定义）

## 7. Support / 覆盖检查

1. 离线数据必须提供行为覆盖报告：
   - 动作分布覆盖
   - 关键状态区间覆盖
   - OOD 参考桶支持度
2. 覆盖不足时，禁止直接进入 `IQL -> SAC` 在线链路。

## 8. 产物与审计

1. 每次离线数据发布必须生成：
   - `dataset_manifest.json`
   - `split_manifest.json`
   - `support_report.json`
2. promotion 评审必须引用以上 manifest，不允许口头声明数据口径。
