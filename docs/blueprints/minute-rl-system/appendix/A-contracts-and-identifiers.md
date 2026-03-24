# 附录 A 契约冻结与唯一键定义

## 1. 唯一键

1. `slot_id = {market_date_local}_{timeframe}_{bar_close_ts_utc}`
2. `decision_id = {strategy_id}_{slot_id}_{policy_model_version}`
3. `execution_id = {decision_id}_{retry_seq}`
4. `transition_id = {decision_id}_{next_slot_id}`
5. `action_id = {decision_id}_{action_seq}`
6. `reward_leg_id = {action_id}_{reward_window_type}_{component_code}_{reward_formula_version}`
7. `reward_id = {action_id}_{reward_window_type}_{reward_formula_version}`

## 2. 幂等与重跑规则

1. 唯一键最小集合：`(strategy_id, account_id, trading_day, slot_id, mode)`。
2. 同一唯一键只允许一个 `effective_transition_set`。
3. 补跑只能产生 `retry_run_id`，禁止覆盖原始 transition。
4. 同一 `slot_id` 出现多动作版本时，该日数据标记无效并阻断晋级。

## 3. 时间因果契约（强制）

1. 首版固定成交起点：`eligible_fill_start_ts = next_bar_open_ts`。
2. 首版固定主奖励窗口：`reward_close_ts = decision_ts + 30min`。
3. 必须满足：`feature_cutoff_ts < decision_ts <= submit_ts < eligible_fill_start_ts <= reward_close_ts`。
4. 若存在 `first_fill_ts`，必须满足 `first_fill_ts >= eligible_fill_start_ts`。
5. 必须满足时钟一致性：`|local_clock - broker_clock| <= 500ms` 且 `|broker_clock - market_clock| <= 500ms`；超阈值 slot 必须 fail-close。
6. `state_t` 禁止访问 `t+1` 字段。
7. `reward_t` 禁止使用 `decision_ts` 时不可见的信息。

## 4. 因果审计 Hard Gate

1. 每次评审随机抽检 `>= 1000` 条 transition。
2. 允许违规数 `= 0`。
3. 任一违规即该 run 无效，禁止参与晋级。

## 5. 必须落盘字段（摘要）

1. 时间与身份：
   - `strategy_id`
   - `market_date_local`
   - `slot_id`
   - `decision_id`
   - `execution_id`
   - `event_ts_utc`
   - `local_clock_ts`
   - `broker_clock_ts`
   - `market_clock_ts`
   - `clock_skew_local_broker_ms`
   - `clock_skew_broker_market_ms`
2. 版本：
   - `feature_schema_version`
   - `reward_formula_version`
   - `simulator_version`
   - `white_box_policy_version`
   - `policy_model_version`
3. 动作：
   - `action_id`
   - `action_before_projection`
   - `action_after_projection`
   - `binding_constraints_count`
   - `binding_constraint_codes`
4. 执行：
   - `submitted_orders`
   - `filled_orders`
   - `rejected_orders`
   - `stale_open_orders`
   - `slippage_bps`
   - `fees_bps`
5. 奖励：
   - `reward_window_type`
   - `reward_leg_id`
   - `reward_raw_terms`
   - `reward_normalized_terms`
   - `reward_final`
   - `reward_id`
6. 训练：
   - `actor_grad_norm`
   - `critic_grad_norm`
   - `update_ratio`
   - `q_gap`
   - `entropy`
   - `nan_or_inf_count`

## 6. 唯一真相源

1. ledger/event store 是训练与评审的唯一真相源。
2. trainer 禁止绕过 ledger 直接读取 broker 实时接口作为训练标签。
3. order/fill/equity 状态写入路径必须唯一，禁止双写。
