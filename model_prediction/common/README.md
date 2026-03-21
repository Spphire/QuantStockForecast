# Model Common

`model_prediction/common` 提供两层共享能力：

- `expert registry + dispatcher`
- `prediction -> signal` 统一契约

核心文件：

- [expert_registry.py](C:/Users/Apricity/Desktop/股票/model_prediction/common/expert_registry.py)
- [run_expert_model.py](C:/Users/Apricity/Desktop/股票/model_prediction/common/run_expert_model.py)
- [signal_interface.py](C:/Users/Apricity/Desktop/股票/model_prediction/common/signal_interface.py)

## 当前注册的 Expert

- `lightgbm`
- `xgboost`
- `catboost`
- `lstm`
- `transformer`
- `ensemble`

## 统一 Expert 调用

```powershell
python model_prediction/common/run_expert_model.py train lightgbm -- INPUT.csv --mode regression
python model_prediction/common/run_expert_model.py predict transformer -- INPUT.csv --model-path ... --reference-metrics ...
python model_prediction/common/run_expert_model.py predict ensemble -- INPUT.csv --prediction-csv expert_b.csv --prediction-csv expert_c.csv
```

这个入口的意义是：

- 外部只关心 `action + model`
- 不需要记每个 expert 自己的脚本路径
- 新 expert 或组合器只要注册到 `expert_registry.py` 就能接入同一套调用方式

## 统一 Signal 契约

不同模型原始输出可能不同：

- 分类模型输出 `pred_probability`
- 回归模型输出 `pred_return`
- ranking 模型输出 `pred_score`

`signal_interface.py` 会把这些差异统一成下游可消费的信号表。

## 标准信号字段

- `date`
- `symbol`
- `score`
- `confidence`
- `horizon`
- `model_name`
- `model_mode`
- `realized_return`

如果原始预测文件里存在，也会尽量保留：

- `close`
- `amount`
- `turnover`
- `volume`
- `pred_label`
- `pred_rank`

## 对下游的意义

只要一个 expert 输出兼容的 `test_predictions.csv`，它就能直接进入：

- `risk_management/white_box`
- 组合构建层
- 后续 ensemble 或投票逻辑

这让 `model_prediction` 可以扩成真正的多 expert 系统，而不是一堆互相割裂的脚本。
