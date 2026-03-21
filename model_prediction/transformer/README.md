# Transformer

`model_prediction/transformer` 提供一条轻量 `PyTorch Transformer` expert，和树模型 expert 共享同一份输出契约。

## 当前能力

- 支持 `classification / regression / ranking`
- 复用统一标准化股票数据
- 训练与推理都输出统一的 `test_predictions.csv`
- 可直接被 `signal_interface` 和 `white_box_risk` 消费

## 关键文件

- [core.py](C:/Users/Apricity/Desktop/股票/model_prediction/transformer/core.py)
  共享特征工程、序列构造、模型和保存/加载逻辑
- [scripts/train_transformer.py](C:/Users/Apricity/Desktop/股票/model_prediction/transformer/scripts/train_transformer.py)
  训练入口
- [scripts/predict_transformer.py](C:/Users/Apricity/Desktop/股票/model_prediction/transformer/scripts/predict_transformer.py)
  推理入口

## 统一调用

```powershell
python model_prediction/common/run_expert_model.py train transformer -- INPUT.csv --mode regression
python model_prediction/common/run_expert_model.py predict transformer -- INPUT.csv --model-path ... --reference-metrics ...
```

## 输出文件

训练后默认落在 `model_prediction/transformer/artifacts/`：

- `prepared_dataset.csv`
- `metrics.json`
- `test_predictions.csv`
- `model.pt`
- `model_metadata.json`
- `feature_stats.json`
- `feature_importance.csv`

推理后会生成：

- `prepared_dataset.csv`
- `predict_summary.json`
- `test_predictions.csv`

## 依赖

这一模块需要 `torch`。

## 当前定位

这条线现在已经不是“规划中的序列模型”，而是已实现的深度 expert。它更适合扮演：

- 序列建模对照组
- 与树模型并行的第二类 alpha 生成器
- 后续多 expert 融合的深度分支
