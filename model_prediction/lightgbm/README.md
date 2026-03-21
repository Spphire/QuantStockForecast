# LightGBM

`model_prediction/lightgbm` 是当前项目最成熟、最完整、已经被真实实验验证的模型模块。

## 当前能力

- 数据检查
- 特征工程
- 时间切分训练
- 分类 / 回归 / ranking 三种模式
- 特征重要性导出
- top-k 回测
- zero-shot 推理

## 关键脚本

- [check_stock_dataset.py](C:/Users/Apricity/Desktop/股票/model_prediction/lightgbm/scripts/check_stock_dataset.py)
  检查标准化数据是否满足建模要求
- [train_lightgbm.py](C:/Users/Apricity/Desktop/股票/model_prediction/lightgbm/scripts/train_lightgbm.py)
  主训练脚本
- [predict_lightgbm.py](C:/Users/Apricity/Desktop/股票/model_prediction/lightgbm/scripts/predict_lightgbm.py)
  用现有模型做 zero-shot 推理
- [backtest_topk.py](C:/Users/Apricity/Desktop/股票/model_prediction/lightgbm/scripts/backtest_topk.py)
  轻量级 top-k 回测

## 当前建模逻辑

### 输入

- 来自 `data_module/fetchers` 的标准化 CSV

### 特征

当前主线特征包括：

- 收益率特征
- 均线偏离特征
- 成交量比率特征
- 波动率特征
- 20 日位置与突破特征
- 市场相对强弱特征
- 横截面分位特征

### 标签

- `classification`
  未来 N 日是否上涨
- `regression`
  未来 N 日收益率
- `ranking`
  按未来收益率做分桶排名标签

## 当前数据切分方式

按时间切分，不随机打乱：

- 训练集：`70%`
- 验证集：`15%`
- 测试集：`15%`

这保证了不会因为随机切分而产生明显的未来信息泄露。

## 当前已验证实验

### A 股

- 单股 baseline
- 多股票回归 / ranking
- 白盒风控与平滑加减仓

### 美股 zero-shot

- 用 A 股训练好的模型直接迁移到美股
- 回归版仍保留一定迁移能力
- ranking 版迁移效果较差

## 输出产物

训练脚本通常会输出：

- `prepared_dataset.csv`
- `metrics.json`
- `test_predictions.csv`
- `feature_importance.csv`
- `model.txt`

推理脚本会输出：

- `prepared_dataset.csv`
- `test_predictions.csv`
- `predict_summary.json`

## 当前定位

这是项目现在的主线基线模型，也是最适合作为后续 XGBoost、CatBoost 和深度学习对照组的模块。

## 当前局限

- 特征工程仍然和训练脚本耦合
- 还没有 walk-forward 训练器
- 还没有把参数搜索系统化
- zero-shot 仍然依赖训练时的原始特征列表
