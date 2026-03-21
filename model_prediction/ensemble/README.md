# Ensemble

`model_prediction/ensemble` 是多专家组合层，不训练独立预测模型，而是把多个 expert 的 `test_predictions.csv` 合并成一份统一信号表，供白盒风控或后续组合层使用。

## 支持的方法

- `mean_score`
- `rank_average`
- `vote`

## 统一调用

```powershell
python model_prediction/common/run_expert_model.py train ensemble -- INPUT.csv --prediction-csv expert_b.csv --prediction-csv expert_c.csv
python model_prediction/common/run_expert_model.py predict ensemble -- INPUT.csv --prediction-csv expert_b.csv --prediction-csv expert_c.csv --method vote
```

`train` 和 `predict` 会走同一套组合逻辑。这里的 `train` 只是为了保留和其它 expert 一致的调用形状，不会拟合一个新的模型参数。

## 输出

- `prepared_dataset.csv`
- `test_predictions.csv`
- `predict_summary.json`
- `ensemble_manifest.json`

其中 `test_predictions.csv` 保持和其它 expert 相同的 signal schema，因此可以直接进入 `white_box_risk`。
