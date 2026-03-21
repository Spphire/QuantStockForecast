# XGBoost

`model_prediction/xgboost` 是 `LightGBM` 的同口径对照模块，目标是让树模型专家可以并行存在，并且输出统一的 `signal` 产物供白盒风控消费。

## 当前能力

- 复用与 `LightGBM` 一致的特征工程
- 复用与 `LightGBM` 一致的时间切分
- 支持 `classification / regression / ranking`
- 输出统一格式的 `prepared_dataset.csv`
- 输出统一格式的 `metrics.json`
- 输出统一格式的 `test_predictions.csv`
- 输出统一格式的 `feature_importance.csv`

## 关键脚本

- [scripts/train_xgboost.py](C:/Users/Apricity/Desktop/股票/model_prediction/xgboost/scripts/train_xgboost.py)
  训练或准备 XGBoost 数据集
- [scripts/predict_xgboost.py](C:/Users/Apricity/Desktop/股票/model_prediction/xgboost/scripts/predict_xgboost.py)
  用现有 XGBoost 模型做 zero-shot 推理

## 与 LightGBM 的对齐方式

XGBoost 模块尽量保持与 LightGBM 相同的调用体验：

- 相同的输入数据
- 相同的 `mode` 选择
- 相同的时间切分
- 相同的输出文件结构

这样做的目的，是让 `risk_management/white_box` 不需要关心底层究竟是哪个 boosting 实现。

## 当前建议用途

- 作为 `LightGBM` 的树模型专家对照组
- 用来比较不同 boosting 实现的信号稳定性
- 作为白盒风控的多专家候选输入

## 运行前提

当前脚本依赖 `xgboost` Python 包。若环境里尚未安装，请先安装依赖后再运行脚本。

## 输出产物

训练脚本会输出：

- `prepared_dataset.csv`
- `metrics.json`
- `test_predictions.csv`
- `feature_importance.csv`
- `model.json`

推理脚本会输出：

- `prepared_dataset.csv`
- `test_predictions.csv`
- `predict_summary.json`

## 当前定位

这一模块不是替代 `LightGBM`，而是补上一个同口径的第二树模型专家，方便后续做 ensemble 或白盒风控对比。
