# 使用说明

这份文档给出当前项目最常见的三种使用方式：研究、实验复盘、paper trading。

## 1. 跑研究基线

适合从标准化数据开始训练单个 expert。

- LightGBM 基线流程：
  [aligned_pipeline.md](C:/Users/Apricity/Desktop/股票/docs/project/aligned_pipeline.md)
- 统一 expert 调度入口：
  [run_expert_model.py](C:/Users/Apricity/Desktop/股票/model_prediction/common/run_expert_model.py)

## 2. 跑多专家实验

适合比较 `lightgbm / xgboost / catboost / lstm / transformer / ensemble`。

- 多 expert 预测模块说明：
  [model_prediction/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/README.md)
- 多专家验证记录：
  [multi_expert_validation.md](C:/Users/Apricity/Desktop/股票/docs/experiments/multi_expert_validation.md)
- 最新多专家报告：
  [us_a_share_multi_expert_report.md](C:/Users/Apricity/Desktop/股票/docs/experiments/us_a_share_multi_expert_report.md)

## 3. 跑 paper trading

适合把风控产出的目标仓位提交到 Alpaca paper 账户。

- 操作手册：
  [paper_trading_daily_manual.md](C:/Users/Apricity/Desktop/股票/docs/project/paper_trading_daily_manual.md)
- 最新验证报告：
  [full_validation_2026-03-22.md](C:/Users/Apricity/Desktop/QuantStockForecast/docs/project/full_validation_2026-03-22.md)
- 当前主线策略：
  [us_zeroshot_a_share_multi_expert_daily.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_zeroshot_a_share_multi_expert_daily.json)
  和
  [us_full_multi_expert_daily.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_full_multi_expert_daily.json)
- 执行模块总览：
  [execution/README.md](C:/Users/Apricity/Desktop/股票/execution/README.md)
- Alpaca 适配器：
  [execution/alpaca/README.md](C:/Users/Apricity/Desktop/股票/execution/alpaca/README.md)
- 产品化 runtime：
  [execution/managed/README.md](C:/Users/Apricity/Desktop/QuantStockForecast/execution/managed/README.md)
  / [run_managed_paper_strategy.py](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/run_managed_paper_strategy.py)
  / [paper_daily.py](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/paper_daily.py)
  / [paper_ops.py](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/paper_ops.py)

## 4. 看实验结论

- A 股实验：
  [experiment_test_report.md](C:/Users/Apricity/Desktop/股票/docs/experiments/experiment_test_report.md)
- 美股 zero-shot：
  [us_zeroshot_experiment_report.md](C:/Users/Apricity/Desktop/股票/docs/experiments/us_zeroshot_experiment_report.md)
- 多专家 zero-shot：
  [us_a_share_multi_expert_report.md](C:/Users/Apricity/Desktop/股票/docs/experiments/us_a_share_multi_expert_report.md)
