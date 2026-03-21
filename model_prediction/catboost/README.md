# CatBoost

`model_prediction/catboost` 是与 `lightgbm` 同口径的真实 `CatBoost` expert。

## 当前能力

- 复用统一标准化数据与目标定义
- 支持 `classification / regression / ranking`
- 支持类别特征输入，当前默认把 `symbol` 作为显式类别列
- 输出统一格式的 `prepared_dataset.csv / metrics.json / test_predictions.csv`
- 可直接接入 `signal_interface` 和 `white_box_risk`

## 关键脚本

- [scripts/train_catboost.py](C:/Users/Apricity/Desktop/股票/model_prediction/catboost/scripts/train_catboost.py)
- [scripts/predict_catboost.py](C:/Users/Apricity/Desktop/股票/model_prediction/catboost/scripts/predict_catboost.py)
- [shared.py](C:/Users/Apricity/Desktop/股票/model_prediction/catboost/shared.py)

## 与其他 Expert 的对齐

CatBoost 模块和 `lightgbm / xgboost` 保持同一套外部体验：

- 相同输入数据
- 相同 `mode`
- 相同时间切分
- 相同产物结构

## 训练示例

```powershell
python model_prediction/common/run_expert_model.py train catboost -- data/interim/...csv --mode regression
```

## 推理示例

```powershell
python model_prediction/common/run_expert_model.py predict catboost -- data/interim/...csv --model-path model_prediction/catboost/artifacts/<run>/model.cbm --reference-metrics model_prediction/catboost/artifacts/<run>/metrics.json
```

## 输出产物

训练后会生成：

- `prepared_dataset.csv`
- `metrics.json`
- `test_predictions.csv`
- `feature_importance.csv`
- `model.cbm`

推理后会生成：

- `prepared_dataset.csv`
- `test_predictions.csv`
- `predict_summary.json`

## 当前定位

这一模块的目标不是替代 `lightgbm`，而是补上一个真正的类别友好树模型 expert，方便后续做：

- 多 expert 对照
- ensemble
- 白盒风控下的专家投票
