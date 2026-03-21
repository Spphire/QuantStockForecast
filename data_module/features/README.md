# Features

`data_module/features` 是预留的特征工程模块，目标是把当前散落在训练脚本里的特征逻辑逐步沉淀出来。

## 计划职责

- 技术指标生产
- 横截面特征生产
- 市场状态特征
- 行业相对强弱特征
- 风格暴露特征
- 文本或事件特征融合后的特征表输出

## 当前现状

当前特征主要还在：

- [train_lightgbm.py](C:/Users/Apricity/Desktop/股票/model_prediction/lightgbm/scripts/train_lightgbm.py)

也就是说，现在是“模型脚本自带特征工程”，而不是“特征层独立供多个模型复用”。

## 为什么后面值得拆出来

- LightGBM、XGBoost、CatBoost 可以共享同一份表格特征
- zero-shot 和正式训练都能走同一套特征生成逻辑
- 更方便做特征版本管理和 ablation

## 推荐未来拆分

- `price_features.py`
- `volume_features.py`
- `cross_sectional_features.py`
- `market_regime_features.py`
- `event_features.py`
- `feature_store.py`

## 当前状态

- 规划中
- 还没有形成单独的 CLI 或统一 API

## 建议

等 LightGBM 的主线特征比较稳定后，优先把它抽到这个模块。这样后面做 XGBoost、CatBoost 和深度学习输入时，重复工作会少很多。
