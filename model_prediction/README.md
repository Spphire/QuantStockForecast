# Model Prediction

`model_prediction` 是项目里的预测层，负责把标准化数据转换成统一格式的模型信号，再交给白盒风控和组合层。

## 当前已实现 Expert

- [lightgbm/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/lightgbm/README.md)
  表格特征主线基线，支持 `classification / regression / ranking`
- [xgboost/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/xgboost/README.md)
  真实 `XGBoost` 树模型 expert，支持 `classification / regression / ranking`
- [catboost/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/catboost/README.md)
  真实 `CatBoost` expert，支持 `classification / regression / ranking`
- [lstm/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/lstm/README.md)
  `PyTorch LSTM` 序列 expert，支持 `regression / classification`
- [transformer/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/transformer/README.md)
  轻量 `PyTorch Transformer` 序列 expert，支持 `classification / regression / ranking`
- [ensemble/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/ensemble/README.md)
  多专家组合层，支持 `mean_score / rank_average / vote`
- [common/README.md](C:/Users/Apricity/Desktop/股票/model_prediction/common/README.md)
  统一 expert 调度与 signal 契约

## 统一调用

现在所有 expert 都可以通过同一个入口调用：

```powershell
python model_prediction/common/run_expert_model.py train lightgbm -- INPUT.csv --mode regression
python model_prediction/common/run_expert_model.py train xgboost -- INPUT.csv --mode regression
python model_prediction/common/run_expert_model.py train catboost -- INPUT.csv --mode regression
python model_prediction/common/run_expert_model.py train lstm -- INPUT.csv --mode regression
python model_prediction/common/run_expert_model.py train transformer -- INPUT.csv --mode regression
python model_prediction/common/run_expert_model.py train ensemble -- INPUT.csv --prediction-csv expert_b.csv

python model_prediction/common/run_expert_model.py predict xgboost -- INPUT.csv --model-path ... --reference-metrics ...
```

统一入口会自动转发到对应 expert 的 `train/predict` 脚本。

## 统一输出契约

所有 expert 的目标都不是直接下单，而是产出统一预测文件：

- `prepared_dataset.csv`
- `metrics.json`
- `test_predictions.csv`

其中 `test_predictions.csv` 至少会包含：

- `date`
- `symbol`
- `close`
- `target_return_*d`
- `pred_probability` 或 `pred_return` 或 `pred_score`

这些字段会被 [signal_interface.py](C:/Users/Apricity/Desktop/股票/model_prediction/common/signal_interface.py) 统一转成标准信号：

- `score`
- `confidence`
- `horizon`
- `model_name`
- `model_mode`

## 与风控层的边界

- 模型层负责找 alpha
- 风控层负责决定 alpha 能不能变成仓位

这个边界保持不变，所以后续新增 expert 不需要直接改执行层。

## 当前验证状态

最新多 expert 冒烟验证见：

- [multi_expert_validation.md](C:/Users/Apricity/Desktop/股票/docs/multi_expert_validation.md)

这轮已经验证：

- 五类 expert 都能独立 `train + predict`
- ensemble 作为组合层可以复用同一调用方式
- 统一入口能正确调度
- `signal_interface` 能统一加载输出
- `white_box_risk` 能直接消费 `xgboost / catboost / lstm / transformer`
