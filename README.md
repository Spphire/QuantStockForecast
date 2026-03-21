# 股票预测项目上下文

这是一个面向 **A 股优先、跨市场可迁移** 的股票研究项目。当前项目已经跑通了从 `数据抓取 -> 标准化 -> 模型训练/zero-shot 预测 -> 白盒风控 -> 回测` 的完整闭环，并且已经在 A 股和美股上做过真实实验。

## 当前目标

- 让 `data_module` 统一管理股票数据拉取、元数据拉取和标准化
- 让 `model_prediction` 专注产生统一格式的 `signal`
- 让 `risk_management` 用白盒规则把 `signal` 转成组合和收益曲线
- 保持每个模块都可以单独迭代，同时通过稳定接口对接

## 当前已验证主线

### A 股

- 数据源：`AKShare + Eastmoney/Sina fallback`
- 研究市场：A 股大盘股池
- 主线模型：`LightGBM regression/ranking`
- 风控方式：白盒规则过滤、行业/流动性约束、平滑加减仓
- 已完成多组曲线实验和实验报告

### 美股 zero-shot

- 数据源：`Stooq` 日线
- 股票池：`configs/stock_universe_us_large_cap_30.txt`
- 做法：直接把 A 股训练好的 LightGBM 模型零样本迁移到美股
- 已验证：
  - `regression` zero-shot 仍有一定迁移能力
  - `ranking` zero-shot 明显弱于回归版
  - 白盒风控和回测链路可以不改架构直接复用

## 项目模块

- [data_module/README.md](C:/Users/Apricity/Desktop/股票/data_module/README.md)
  数据层总览
- [data_module/common/README.md](C:/Users/Apricity/Desktop/股票/data_module/common/README.md)
  共享 schema 与标准化契约
- [data_module/fetchers/README.md](C:/Users/Apricity/Desktop/股票/data_module/fetchers/README.md)
  数据抓取与元数据抓取
- [data_module/cleaning/README.md](C:/Users/Apricity/Desktop/股票/data_module/cleaning/README.md)
  清洗模块规划
- [data_module/crawlers/README.md](C:/Users/Apricity/Desktop/股票/data_module/crawlers/README.md)
  爬虫模块规划
- [data_module/features/README.md](C:/Users/Apricity/Desktop/股票/data_module/features/README.md)
  特征层规划
- [model_prediction/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/README.md)
  预测层总览
- [model_prediction/common/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/common/README.md)
  统一 signal 接口
- [model_prediction/lightgbm/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/lightgbm/README.md)
  LightGBM 已实现主线
- [model_prediction/xgboost/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/xgboost/README.md)
  XGBoost 规划
- [model_prediction/catboost/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/catboost/README.md)
  CatBoost 规划
- [model_prediction/lstm/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/lstm/README.md)
  LSTM 规划
- [model_prediction/transformer/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/transformer/README.md)
  Transformer 规划
- [risk_management/README.md](C:/Users/Apricity/Desktop/股票/risk_management/README.md)
  风控层总览
- [risk_management/common/README.md](C:/Users/Apricity/Desktop/股票/risk_management/common/README.md)
  风控共享能力规划
- [risk_management/white_box/README.md](C:/Users/Apricity/Desktop/股票/risk_management/white_box/README.md)
  白盒风控已实现主线
- [execution/README.md](C:/Users/Apricity/Desktop/股票/execution/README.md)
  实战执行层总览
- [execution/common/README.md](C:/Users/Apricity/Desktop/股票/execution/common/README.md)
  执行层共享模型和校验
- [execution/alpaca/README.md](C:/Users/Apricity/Desktop/股票/execution/alpaca/README.md)
  Alpaca 适配器和双 paper strategy

## 关键报告

- [docs/experiment_test_report.md](C:/Users/Apricity/Desktop/股票/docs/experiment_test_report.md)
  A 股实验报告
- [docs/us_zeroshot_experiment_report.md](C:/Users/Apricity/Desktop/股票/docs/us_zeroshot_experiment_report.md)
  美股 zero-shot 实验报告
- [docs/aligned_pipeline.md](C:/Users/Apricity/Desktop/股票/docs/aligned_pipeline.md)
  当前推荐流程

## 当前最重要的接口约束

- 数据标准化输出要遵守 `data_module/common/stock_schema.py`
- 预测输出要能被 `model_prediction/common/signal_interface.py` 识别
- 白盒风控默认消费模型产出的 `test_predictions.csv`
- 执行层默认消费 `risk_positions.csv` 的最新调仓目标

## 当前现实结论

- 这个项目已经不是“只有想法和结构”，而是有可复现实验结果的研究骨架
- 目前最稳的方向仍然是：
  - 市场先做日线股票池
  - 模型先做横截面收益预测
  - 组合和风险约束放在模型外部
- 未来如果继续扩展，最值得优先做的是：
  - 更完整的特征工程模块
  - 更严格的 walk-forward 验证
  - 更真实的组合与执行约束
