# 项目架构说明

这个项目目前按 `数据 -> 预测 -> 风控 -> 执行` 四层组织，研究文档和开发日志单独放在 `docs/`。

## 模块分层

- `data_module`
  负责抓数、标准化、元数据和特征准备
- `model_prediction`
  负责训练单 expert 或 ensemble，并输出统一 `signal`
- `risk_management`
  负责白盒规则过滤、限仓、持仓构造和组合层约束
- `execution`
  负责把目标仓位翻译成 Alpaca paper/live 可执行计划

## 核心边界

- 数据契约：
  [stock_schema.py](C:/Users/Apricity/Desktop/股票/data_module/common/stock_schema.py)
- 信号契约：
  [signal_interface.py](C:/Users/Apricity/Desktop/股票/model_prediction/common/signal_interface.py)
- 风控输出：
  `risk_positions.csv` / `risk_periods.csv`
- 执行状态：
  `execution/runtime/*` 与 `execution/state/*`

## 当前推荐链路

1. 数据模块生成标准化 CSV。
2. 预测模块训练 expert 或 ensemble，并产出 `test_predictions.csv`。
3. 白盒风控把预测结果转成目标仓位和风险约束后的组合。
4. 执行层根据账户资金、已有持仓和目标权重生成订单。

## 当前文档分工

- 项目说明：`docs/project`
- 实验报告：`docs/experiments`
- 开发日志：`docs/development_logs`

## 相关入口

- [usage_guide.md](C:/Users/Apricity/Desktop/股票/docs/project/usage_guide.md)
- [model_prediction/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/README.md)
- [white_box README.md](C:/Users/Apricity/Desktop/股票/risk_management/white_box/README.md)
- [execution README.md](C:/Users/Apricity/Desktop/股票/execution/README.md)
