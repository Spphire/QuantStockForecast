# 26 状态观测契约（State Contract v1）

更新时间：`2026-03-24`（`Asia/Shanghai`）

## 1. 目标

1. 固定分钟级 RL 训练与评审使用的 `state_t` 构造口径。
2. 保证 `state_t` 全部字段满足 as-of 因果规则，可被审计复现。
3. 防止训练、评审、线上执行使用不同观测定义。

## 2. 观测分组（v1）

1. 市场微观统计：近 N 个 bar 的收益、波动、成交量、点差代理、成交额变化率。
2. 策略输出状态：expert 原始分数、投影后权重、前一 slot 动作向量。
3. 执行状态：`reject_rate_rolling`、`open_order_age_p95`、`fill_latency_p95`、`slippage_bps_rolling`。
4. 风控状态：`gross_exposure`、`turnover`、`binding_rate_by_dimension`、`clip_ratio`。
5. 账户状态：`equity`、`cash`、`buying_power`、核心持仓偏差。
6. 时钟状态：`local/broker/market` 偏差字段与 `is_open`。

## 3. As-Of 规则（强制）

1. 每个字段必须落 `feature_asof_ts`，且满足 `feature_asof_ts <= feature_cutoff_ts`。
2. 任一字段来自 `t+1` 或未来事件，当前 slot 直接标记 `invalid_due_to_causality_violation`。
3. 归一化统计量必须落 `norm_asof_ts`，并满足 `norm_asof_ts <= feature_cutoff_ts`。

## 4. 缺失值与异常值策略

1. 缺失值仅允许两种策略：`forward_fill_with_max_age` 或 `safe_default`，必须记录 `impute_mode`。
2. 超过 `max_age` 的前向填充视为无效观测，当前 slot 进入 `invalid` 或 `shadow-only`。
3. 非法值（负价格、`high<low` 等）必须在进入 state 前拦截，不得静默截断。

## 5. 归一化与版本

1. 归一化模式固定为 `EWMA z-score`（收益/成本）+ 预算归一化（风险项）。
2. 统一版本字段：
   - `feature_schema_version`
   - `state_contract_version = state_contract_v1`
   - `normalization_version`
3. 任意版本变更都必须切新评审窗口，不得和旧窗口样本拼接。

## 6. 验收与阻断

1. 因果审计抽检 `>=1000` 条时必须包含 state as-of 校验。
2. `state_non_null_rate`、`state_freshness_rate`、`state_contract_compat_rate` 三项必须达标后才能开训。
3. state 契约不匹配时，阻断训练与晋级，允许 `shadow-only` 记录。
