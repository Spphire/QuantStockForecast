# 架构总览

## 分层职责

| 层级 | 目录 | 主要职责 | 典型输出 |
|---|---|---|---|
| 数据层 | `data_module/` | 拉取行情与元数据、标准化 schema | `data/interim/.../*.csv` |
| 预测层 | `model_prediction/` | 训练/推理 expert 与 ensemble | `test_predictions.csv`、`metrics.json` |
| 风控层 | `risk_management/white_box/` | 信号过滤、选股、仓位与回测统计 | `risk_positions.csv`、`risk_summary.json` |
| 执行层 | `execution/` | 计划构建、下单、对账、运维 | `execution_plan.json`、`run_summary.json` |

## 核心接口契约

### 1) 数据 -> 预测

- 标准化由 `data_module/common/stock_schema.py` 定义。
- 最小必需字段：`date, open, high, low, close, volume`。
- 常用附加字段：`symbol, amount, turnover, provider, adjust`。

### 2) 预测 -> 风控

- 风控默认消费 `test_predictions.csv`。
- 预测文件需包含：`date, symbol` + 预测列之一：
  - `pred_probability`（classification）
  - `pred_return`（regression）
  - `pred_score`（ranking）
- `model_prediction/common/signal_interface.py` 负责统一为标准 signal。

### 3) 风控 -> 执行

- 执行默认消费 `risk_positions.csv`（及可选 `risk_actions.csv`）。
- 关键字段：`rebalance_date, symbol, target_weight, previous_weight, action`。
- 策略 JSON 的 `source.path` 指向该文件。

## 运行时落盘约定

- 研究/预测产物：`model_prediction/<expert>/artifacts/<run_name>/`
- 风控产物：`risk_management/white_box/runtime/<strategy>/`
- 执行运行记录：`execution/runtime/<strategy>/<timestamp>/`
- 执行最新快照：`execution/runtime/<strategy>/latest/`
- 执行状态：`execution/state/<strategy>/`
- 账本：`artifacts/paper_trading/<strategy>/paper_ledger.sqlite3`

## 当前主线策略

- `execution/strategies/us_zeroshot_a_share_multi_expert_daily.json`
- `execution/strategies/us_full_multi_expert_daily.json`

两者都采用 `source.type = risk_positions_csv`，由白盒风控产出目标仓位后再执行。

