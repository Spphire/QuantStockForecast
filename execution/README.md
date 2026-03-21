# Execution

`execution` 是项目里的实战板块，负责把模型和白盒风控输出的目标仓位，变成可提交给券商的订单计划。

## 设计原则

- 不让模型直接下单
- 优先消费 `risk_management` 产出的目标仓位
- 先做 `paper-first`
- 同一执行层可以服务多个策略账户

## 当前结构

- [common/README.md](C:/Users/Apricity/Desktop/股票/execution/common/README.md)
  共享数据结构、风控校验和持仓对账
- [alpaca/README.md](C:/Users/Apricity/Desktop/股票/execution/alpaca/README.md)
  Alpaca 券商适配器
- [strategies/us_zeroshot_a_share_regression_balanced.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_zeroshot_a_share_regression_balanced.json)
  A 股训练后 zero-shot 到美股的 paper 主策略
- [strategies/us_full_regression_balanced.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_full_regression_balanced.json)
  美股全量训练的 paper 策略
- [scripts/run_paper_strategy.py](C:/Users/Apricity/Desktop/股票/execution/scripts/run_paper_strategy.py)
  生成或提交 paper 订单计划
- [scripts/compare_paper_strategies.py](C:/Users/Apricity/Desktop/股票/execution/scripts/compare_paper_strategies.py)
  对比两条实战策略的上游表现和当前计划
- [scripts/show_strategy_state.py](C:/Users/Apricity/Desktop/股票/execution/scripts/show_strategy_state.py)
  查看某条策略最新状态和订单流水

## 当前策略线

### Strategy A

- `us_zeroshot_a_share_regression_balanced`
- 上游来源：A 股训练回归模型 zero-shot 到美股
- 上游风控来源：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/us_zeroshot_aligned_suite/regression_balanced/risk_summary.json)

### Strategy B

- `us_full_regression_balanced`
- 上游来源：美股全量历史训练的回归模型
- 上游风控来源：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/us_full_suite/regression_balanced/risk_summary.json)

## 当前推荐用法

先 dry-run 生成两条计划：

```powershell
python execution/scripts/run_paper_strategy.py execution/strategies/us_zeroshot_a_share_regression_balanced.json
python execution/scripts/run_paper_strategy.py execution/strategies/us_full_regression_balanced.json
python execution/scripts/compare_paper_strategies.py execution/strategies/us_zeroshot_a_share_regression_balanced.json execution/strategies/us_full_regression_balanced.json
```

等你真的开好两个 Alpaca paper account 后，再把 `--submit` 打开。

## 当前边界

这层目前只负责：

- 读取目标仓位
- 校验执行安全规则
- 计算应下订单
- 调用 Alpaca REST API 提交订单
- 保存执行日志

它还没有实现真正的实时成交监听和盘中再平衡，这部分留给后续的 websocket/stream 模块。

## 当前执行默认值

`daily` 策略现在默认走更稳的执行方式：

- 买入按 `notional` 提交，优先锁住预算
- 卖出按 `qty` 提交，优先精确减仓
- `buying_power_buffer=0.97`
  默认只拿账户权益的 `97%` 做目标仓位，主动留一点现金缓冲
- `max_buy_retries=1`
  如果买单提交失败，会自动缩量一次再重试

即使 Alpaca 前端里 `buy notional` 订单看起来 `qty` 是空的，本地计划文件还是会保留：

- `submit_notional`
- `estimated_qty`

对应文件在：

- `execution/runtime/<strategy_id>/latest/order_intents.csv`
- `execution/runtime/<strategy_id>/latest/submission_attempts.json`
- `execution/runtime/<strategy_id>/latest/submitted_order_statuses.json`

## 重启后的状态恢复

当前执行层已经会把状态持久化到：

- `execution/runtime/<strategy_id>/<timestamp>/`
  每次运行的独立产物
- `execution/runtime/<strategy_id>/latest/`
  最近一次运行的快照
- `execution/state/<strategy_id>/latest_state.json`
  最近一次运行的状态摘要
- `execution/state/<strategy_id>/order_journal.csv`
  累积的订单流水

如果你想在关闭进程后快速看当前策略状态，可以运行：

```powershell
python execution/scripts/show_strategy_state.py us_zeroshot_a_share_daily
python execution/scripts/show_strategy_state.py us_full_daily
```
