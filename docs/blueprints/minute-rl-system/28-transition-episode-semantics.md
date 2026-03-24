# 28 Transition 与 Episode 语义契约（v1）

更新时间：`2026-03-24`（`Asia/Shanghai`）

## 1. Transition 定义

1. 标准条目：
   - `(state_t, action_t, reward_t, state_t+1, done_t, info_t)`
2. 关键身份：
   - `slot_id`
   - `decision_id`
   - `execution_id`
   - `transition_id`
   - `reward_leg_id`

## 2. Reward 窗口闭合规则

1. 主训练窗口固定 `30min delayed`。
2. `5min delayed` 仅用于诊断，不作为主训练目标。
3. 当 slot 被判 invalid 时，必须传播作废到对应 `reward_close_ts` 内的延迟奖励腿。

## 3. Done / Truncation 规则

1. `done_t=true` 情况：
   - 交易日结束（收盘闭合）
   - 强制策略终止（kill switch / 账户不可交易）
2. `truncated_t=true` 情况：
   - 停牌/熔断导致窗口无法闭合
   - 数据批次无效导致当前 episode 中断
3. `done` 与 `truncated` 必须分开落盘，不得混用。

## 4. 部分成交与无成交语义

1. 部分成交：
   - 多 fill 事件可对应同一 `execution_id`
   - 但同一 `reward_leg_id` 只能归一个 `action_id`
2. 无成交：
   - 保留执行成本/拒单等即时项
   - 延迟收益项按规则可为 0 或缺省，但必须显式标记原因码

## 5. 折扣与bootstrap边界

1. `gamma` 在 `dataset_manifest` 中固定版本记录（默认建议 `0.99`）。
2. 跨 `done` 状态禁止 bootstrap；`truncated` 仅按定义规则允许有限 bootstrap。
3. 评审与训练必须使用同一 `bootstrap_boundary_version`。

## 6. 跨时段边界

1. 跨收盘不得把下一个交易日数据并入同一 episode。
2. 半天市、节假日前后必须按交易日边界闭合 episode。
3. 午休（若市场存在）需按市场时段规则显式处理，不得隐式拼接。

## 7. 验收

1. 通过 `transition_semantics_audit` 校验 `done/truncated` 一致性。
2. 通过 reward lineage 校验 `reward_leg_id` 唯一归属。
3. 通过跨日检查校验无 episode 漏闭合与错拼接。
