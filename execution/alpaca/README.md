# Alpaca

`execution/alpaca` 负责把统一的执行计划转成 Alpaca API 调用。

## 当前文件

- [client.py](C:/Users/Apricity/Desktop/股票/execution/alpaca/client.py)
  REST 客户端与凭证加载
- [asset_guard.py](C:/Users/Apricity/Desktop/股票/execution/alpaca/asset_guard.py)
  资产可交易性检查
- [order_router.py](C:/Users/Apricity/Desktop/股票/execution/alpaca/order_router.py)
  从 order intent 生成 Alpaca 下单提交
- [account_monitor.py](C:/Users/Apricity/Desktop/股票/execution/alpaca/account_monitor.py)
  账户和持仓快照辅助
- [stream_listener.py](C:/Users/Apricity/Desktop/股票/execution/alpaca/stream_listener.py)
  预留的成交流监听占位

## 环境变量

当前每条策略建议一个单独的环境变量前缀：

- `ALPACA_ZERO_SHOT_API_KEY`
- `ALPACA_ZERO_SHOT_SECRET_KEY`
- `ALPACA_ZERO_SHOT_BASE_URL`
- `ALPACA_US_FULL_API_KEY`
- `ALPACA_US_FULL_SECRET_KEY`
- `ALPACA_US_FULL_BASE_URL`

当前这两个前缀默认对应的是：

- `ALPACA_ZERO_SHOT`
  [us_zeroshot_a_share_multi_expert_daily.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_zeroshot_a_share_multi_expert_daily.json)
- `ALPACA_US_FULL`
  [us_full_multi_expert_daily.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_full_multi_expert_daily.json)

默认 `BASE_URL` 可以填：

- paper: `https://paper-api.alpaca.markets`
- live: `https://api.alpaca.markets`

## 本地配置文件

当前执行层还支持从本地配置文件读取凭证：

- [alpaca_accounts.local.json](C:/Users/Apricity/Desktop/股票/configs/alpaca_accounts.local.json)

读取顺序是：

1. 先读环境变量
2. 环境变量缺失时，再读本地 `configs/alpaca_accounts.local.json`

这让你后面可以直接运行脚本，而不需要每次手动设置环境变量。

注意：

- 这个本地文件现在包含真实密钥
- 不要分享给别人
- 如果后面把项目同步到远程仓库，务必把这个文件排除掉或删除

## 当前限制

- 当前只实现了 REST 侧下单和查询
- websocket 成交监听还没接真实逻辑
- 推荐默认只开 `paper`，不要先开 `live`

## 当前执行语义

`daily` 策略默认使用 `hybrid` 下单模式：

- `buy -> notional`
- `sell -> qty`

这样做的原因是：

- 买入更怕价格跳涨导致超预算，所以按金额更稳
- 卖出更关心减掉多少仓位，所以按股数更直观

现在客户端还会额外做这些动作：

- 在本地配置里应用 `buying_power_buffer`
- 保存 `submission_attempts.json`
- 保存 `submitted_order_statuses.json`
- 在 `show_strategy_state.py` 里展示最近订单状态

## 当前运行状态

截至 `2026-03-22`，两个 paper 账户已经从旧的 `LightGBM daily` 切到了 `mixed-expert ensemble daily`：

- `ALPACA_ZERO_SHOT`
  对应 `A股训练五专家 -> 美股 zero-shot`
- `ALPACA_US_FULL`
  对应 `美股全量训练五专家 -> 美股执行`

最新状态和订单流水分别保存在：

- [us_zeroshot latest_state.json](C:/Users/Apricity/Desktop/股票/execution/state/us_zeroshot_a_share_multi_expert_daily/latest_state.json)
- [us_zeroshot order_journal.csv](C:/Users/Apricity/Desktop/股票/execution/state/us_zeroshot_a_share_multi_expert_daily/order_journal.csv)
- [us_full latest_state.json](C:/Users/Apricity/Desktop/股票/execution/state/us_full_multi_expert_daily/latest_state.json)
- [us_full order_journal.csv](C:/Users/Apricity/Desktop/股票/execution/state/us_full_multi_expert_daily/order_journal.csv)
