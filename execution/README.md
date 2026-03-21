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
- [strategies/us_zeroshot_a_share_multi_expert_daily.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_zeroshot_a_share_multi_expert_daily.json)
  A 股训练五专家 ensemble 的美股 zero-shot 日常实战策略
- [strategies/us_full_multi_expert_daily.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_full_multi_expert_daily.json)
  美股全量训练五专家 ensemble 的日常实战策略
- [strategies/us_zeroshot_a_share_regression_balanced.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_zeroshot_a_share_regression_balanced.json)
  历史研究/实验对照策略
- [strategies/us_full_regression_balanced.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_full_regression_balanced.json)
  历史研究/实验对照策略
- [scripts/run_paper_strategy.py](C:/Users/Apricity/Desktop/股票/execution/scripts/run_paper_strategy.py)
  生成或提交 paper 订单计划
- [scripts/run_managed_paper_strategy.py](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/run_managed_paper_strategy.py)
  使用产品化 runtime 生成/提交订单，并把 run manifest、decision、order、fill、equity snapshot 写入 SQLite ledger
- [managed/README.md](C:/Users/Apricity/Desktop/QuantStockForecast/execution/managed/README.md)
  产品级 runtime 的正式边界说明与模块入口
- [scripts/compare_paper_strategies.py](C:/Users/Apricity/Desktop/股票/execution/scripts/compare_paper_strategies.py)
  对比两条实战策略的上游表现和当前计划
- [scripts/show_strategy_state.py](C:/Users/Apricity/Desktop/股票/execution/scripts/show_strategy_state.py)
  查看某条策略最新状态和订单流水
- [scripts/paper_daily.py](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/paper_daily.py)
  scheduler 友好的 preflight + run shell
- [scripts/paper_smoke.py](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/paper_smoke.py)
  一次性 smoke harness
- [scripts/paper_ops.py](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/paper_ops.py)
  读取 SQLite ledger 做 latest-run / open-orders / run-summary 检查

## 当前策略线

当前 paper 账户主线已经切到 `mixed-expert ensemble`，不是之前的单一 `LightGBM daily`。

### Strategy A

- `us_zeroshot_a_share_multi_expert_daily`
- 上游来源：A 股训练的 `lightgbm / xgboost / catboost / lstm / transformer`
- 聚合方式：`ensemble_mean_score`
- 最新风控来源：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/runtime/us_zeroshot_a_share_multi_expert_daily/risk_summary.json)
- 最新执行状态：
  [latest_state.json](C:/Users/Apricity/Desktop/股票/execution/state/us_zeroshot_a_share_multi_expert_daily/latest_state.json)

历史研究对照：

- `us_zeroshot_a_share_regression_balanced`
- 上游来源：A 股训练单模型 zero-shot 到美股
- 上游风控来源：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/us_zeroshot_aligned_suite/regression_balanced/risk_summary.json)

### Strategy B

- `us_full_multi_expert_daily`
- 上游来源：美股全量训练的 `lightgbm / xgboost / catboost / lstm / transformer`
- 聚合方式：`ensemble_mean_score`
- 最新风控来源：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/runtime/us_full_multi_expert_daily/risk_summary.json)
- 最新执行状态：
  [latest_state.json](C:/Users/Apricity/Desktop/股票/execution/state/us_full_multi_expert_daily/latest_state.json)

历史研究对照：

- `us_full_regression_balanced`
- 上游来源：美股全量训练的单模型回归策略
- 上游风控来源：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/us_full_suite/regression_balanced/risk_summary.json)

## 当前推荐用法

先 dry-run 生成两条计划：

```powershell
python execution/scripts/run_paper_strategy.py execution/strategies/us_zeroshot_a_share_multi_expert_daily.json
python execution/scripts/run_paper_strategy.py execution/strategies/us_full_multi_expert_daily.json
python execution/scripts/compare_paper_strategies.py execution/strategies/us_zeroshot_a_share_multi_expert_daily.json execution/strategies/us_full_multi_expert_daily.json
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
python execution/scripts/show_strategy_state.py us_zeroshot_a_share_multi_expert_daily
python execution/scripts/show_strategy_state.py us_full_multi_expert_daily
```

## 新的产品化运行时

除了原先的轻量脚本，这个仓库现在还带了一套更偏生产运维的 paper runtime。

推荐直接使用模块入口：

- `python -m execution.managed.apps.run_multi_expert_paper execution/strategies/us_zeroshot_a_share_multi_expert_daily.json`
- `python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json run`
- `python -m execution.managed.apps.paper_smoke execution/strategies/us_zeroshot_a_share_multi_expert_daily.json`
- `python -m execution.managed.apps.paper_ops execution/strategies/us_zeroshot_a_share_multi_expert_daily.json latest-run`

兼容层脚本 `execution/scripts/*.py` 仍然保留，但它们现在只是 thin wrapper，方便已有调度器沿用旧调用方式。

这套 runtime 会额外维护：

- `artifacts/paper_trading/<strategy_id>/paper_ledger.sqlite3`
- run manifest
- pre-trade order decision
- broker recovery / reconciliation 结果
- equity snapshot 与 operator-friendly healthcheck

同时，如果策略 `source.path` 指向 `risk_positions.csv`，执行层现在会自动读取同目录下的 `risk_actions.csv`：

- `target_weight > 0` 的持仓目标仍然来自 `risk_positions.csv`
- `action=exit` 且目标权重为 `0` 的清仓目标会从 `risk_actions.csv` 自动补进执行计划

这样可以避免白盒风控里已经判定清仓的 symbol，在执行层因为只读 `risk_positions.csv` 而漏掉卖单。
