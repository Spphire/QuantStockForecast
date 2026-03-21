# Multi-Expert Validation

这份文档记录 `model_prediction` 多 expert 系统的第一轮统一冒烟验证结果。

## 验证目标

- 确认 `lightgbm / xgboost / catboost / lstm / transformer` 都有可执行训练入口
- 确认统一入口 [run_expert_model.py](C:/Users/Apricity/Desktop/股票/model_prediction/common/run_expert_model.py) 可正确调度
- 确认所有 expert 的 `test_predictions.csv` 都能被 [signal_interface.py](C:/Users/Apricity/Desktop/股票/model_prediction/common/signal_interface.py) 读取
- 确认 [run_white_box_risk.py](C:/Users/Apricity/Desktop/股票/risk_management/white_box/scripts/run_white_box_risk.py) 能直接消费这些输出

## 验证数据

- 输入数据：
  [large_cap_20200101_20241231_hfq_normalized.csv](C:/Users/Apricity/Desktop/股票/data/interim/akshare/universes/large_cap_20200101_20241231_hfq_normalized.csv)
- 市场：A 股
- 股票池：10 只大盘股
- 预测任务：`future 5-day return regression`

## 统一调用方式

示例：

```powershell
python model_prediction/common/run_expert_model.py train xgboost -- INPUT.csv --mode regression
python model_prediction/common/run_expert_model.py predict xgboost -- INPUT.csv --model-path ... --reference-metrics ...
```

同样的调用模式也适用于 `catboost / lstm / transformer`。

## 训练产物

- `xgboost`：
  [metrics.json](C:/Users/Apricity/Desktop/股票/model_prediction/xgboost/artifacts/smoke_large_cap_reg/metrics.json)
- `catboost`：
  [metrics.json](C:/Users/Apricity/Desktop/股票/model_prediction/catboost/artifacts/smoke_large_cap_reg/metrics.json)
- `lstm`：
  [metrics.json](C:/Users/Apricity/Desktop/股票/model_prediction/lstm/artifacts/smoke_large_cap_reg/metrics.json)
- `transformer`：
  [metrics.json](C:/Users/Apricity/Desktop/股票/model_prediction/transformer/artifacts/smoke_large_cap_reg/metrics.json)

## 推理产物

- `xgboost`：
  [test_predictions.csv](C:/Users/Apricity/Desktop/股票/model_prediction/xgboost/artifacts/smoke_large_cap_reg_pred/test_predictions.csv)
- `catboost`：
  [test_predictions.csv](C:/Users/Apricity/Desktop/股票/model_prediction/catboost/artifacts/smoke_large_cap_reg_pred/test_predictions.csv)
- `lstm`：
  [test_predictions.csv](C:/Users/Apricity/Desktop/股票/model_prediction/lstm/artifacts/smoke_large_cap_reg_pred/test_predictions.csv)
- `transformer`：
  [test_predictions.csv](C:/Users/Apricity/Desktop/股票/model_prediction/transformer/artifacts/smoke_large_cap_reg_pred/test_predictions.csv)

## 模型层结果摘要

| expert | test rows | symbols | key metric |
| --- | ---: | ---: | --- |
| xgboost | 1730 | 10 | `correlation = 0.1122` |
| catboost | 1820 | 10 | `correlation = -0.0664` |
| lstm | 1820 | 10 | `pearson_correlation = 0.0645` |
| transformer | 1820 | 10 | `correlation = -0.0298` |

补充说明：

- `xgboost` 当前这轮 smoke 的相关性最好，但白盒回测收益非常高，后续需要重点检查是否存在过拟合或排序过于激进的问题。
- `catboost` 这轮表现偏弱，但链路完整，适合作为类别友好树模型 expert 留作对照。
- `lstm` 和 `transformer` 都已经完成真实 `train + predict`，不再是占位目录。

## 白盒风控兼容性验证

四个 expert 都已经进入白盒风控：

- `xgboost`：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/expert_smoke/xgboost/risk_summary.json)
- `catboost`：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/expert_smoke/catboost/risk_summary.json)
- `lstm`：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/expert_smoke/lstm/risk_summary.json)
- `transformer`：
  [risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/expert_smoke/transformer/risk_summary.json)

在统一参数 `top_k=3 / rebalance_step=5 / cost=10bps` 下，这轮 smoke 的结果大致如下：

| expert | total return | benchmark | excess | max drawdown |
| --- | ---: | ---: | ---: | ---: |
| xgboost | 5.9777 | 0.3502 | 5.6275 | -0.2329 |
| catboost | 0.0642 | 0.1820 | -0.1178 | -0.5055 |
| lstm | 0.3245 | 0.1854 | 0.1391 | -0.4563 |
| transformer | 0.9075 | 0.1854 | 0.7221 | -0.5511 |

## 当前结论

- 多 expert 结构已经从“目录规划”升级为“真实可运行系统”
- `xgboost / catboost / lstm / transformer` 都已经完成统一入口、统一预测产物、统一 signal、统一白盒风控对接
- 从工程视角，新增 expert 的最低门槛已经明确：
  1. 实现 `train/predict`
  2. 输出标准 `test_predictions.csv`
  3. 在 `expert_registry.py` 注册
  4. 用 `signal_interface + white_box_risk` 做一轮统一验证

## 当前保留意见

- 这是冒烟验证，不是最终策略结论
- `xgboost` 当前 smoke 收益异常高，只能说明链路已通，不能直接当作研究结论
- 深度模型目前只是轻量训练参数，后续还需要更正式的调参与滚动验证
