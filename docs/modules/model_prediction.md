# 模块说明：model_prediction

## 职责

`model_prediction` 负责 expert 训练/推理与 ensemble 聚合，输出可被风控消费的预测结果。

## 模块结构

- `model_prediction/common/`
  - `expert_registry.py`：统一注册 expert 入口
  - `run_expert_model.py`：统一 train/predict 调度
  - `signal_interface.py`：预测输出标准化
- `model_prediction/<expert>/scripts/`
  - `train_*.py`：训练
  - `predict_*.py`：零样本或推理
- `model_prediction/ensemble/scripts/predict_ensemble.py`
  - 聚合多个 expert 预测

当前已接入 expert：

- `lightgbm`
- `xgboost`
- `catboost`
- `lstm`
- `transformer`
- `ensemble`

## 产物约定

每次运行通常输出到 `model_prediction/<expert>/artifacts/<run_name>/`，核心文件：

- `prepared_dataset.csv`
- `metrics.json`
- `test_predictions.csv`
- `model.*`（训练场景）

## 统一调度命令

训练（示例：LightGBM）：

```powershell
python model_prediction/common/run_expert_model.py train lightgbm -- data/interim/demo/sample_normalized.csv --mode regression --horizon 5
```

推理（示例：LightGBM）：

```powershell
python model_prediction/common/run_expert_model.py predict lightgbm -- data/interim/demo/sample_normalized.csv --model-path model_prediction/lightgbm/artifacts/<run>/model.txt --reference-metrics model_prediction/lightgbm/artifacts/<run>/metrics.json
```

## Ensemble 入口

```powershell
python model_prediction/ensemble/scripts/predict_ensemble.py model_prediction/lightgbm/artifacts/<run>/test_predictions.csv --prediction-csv model_prediction/xgboost/artifacts/<run>/test_predictions.csv --prediction-csv model_prediction/catboost/artifacts/<run>/test_predictions.csv --prediction-csv model_prediction/lstm/artifacts/<run>/test_predictions.csv --prediction-csv model_prediction/transformer/artifacts/<run>/test_predictions.csv --method mean_score --min-experts 5 --model-name ensemble_mean_score --output-dir model_prediction/ensemble/artifacts/<run>
```

