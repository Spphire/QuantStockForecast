# LSTM

`model_prediction/lstm` 是项目里的序列建模模块，提供一个可直接被白盒风控消费的 PyTorch 基线。

## 当前定位

- 用过去 `N` 天的 OHLCV 和衍生特征序列做预测
- 与 `lightgbm` 形成“表格特征 vs 序列特征”的对照
- 输出和现有 `signal_interface` 兼容的 `test_predictions.csv`

## 当前已实现

- [scripts/train_lstm.py](C:/Users/Apricity/Desktop/股票/model_prediction/lstm/scripts/train_lstm.py)
- [scripts/predict_lstm.py](C:/Users/Apricity/Desktop/股票/model_prediction/lstm/scripts/predict_lstm.py)
- [core.py](C:/Users/Apricity/Desktop/股票/model_prediction/lstm/core.py)

## 输入输出

### 输入

- 共享的标准化股票数据
- 与 `lightgbm` 同一套特征工程和时间切分逻辑

### 输出

- `prepared_dataset.csv`
- `metrics.json`
- `test_predictions.csv`
- `model.pt`

其中 `model.pt` 是可直接用于推理的 PyTorch checkpoint，包含模型权重、训练配置、特征列和归一化统计量。

## 支持模式

- `regression`
- `classification`

## 与白盒风控的对接

只要输出里包含这些字段，就可以直接接入 `risk_management/white_box`：

- `date`
- `symbol`
- `pred_return` 或 `pred_probability`
- `close`
- `amount`
- `turnover`
- `volume`
- `target_return_*`

## 推荐用法

先用 `regression` 跑通，再按需要切 `classification`。

示例：

```powershell
python model_prediction/lstm/scripts/train_lstm.py data/interim/stooq/universes/us_large_cap_30_20200101_20251231_hfq_normalized.csv --mode regression
python model_prediction/lstm/scripts/predict_lstm.py data/interim/stooq/universes/us_large_cap_30_20200101_20251231_hfq_normalized.csv --model-path model_prediction/lstm/artifacts/<run>/model.pt --reference-metrics model_prediction/lstm/artifacts/<run>/metrics.json
```

## 设计说明

- 训练和推理都使用同一组特征工程
- 特征标准化只用训练集统计量
- 序列窗口默认长度为 `20`
- 模型采用 LSTM 编码器加轻量回归头
