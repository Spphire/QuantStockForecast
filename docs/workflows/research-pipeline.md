# 工作流：夜间研究流水线

## 目标

在美股收盘后自动完成以下步骤：

1. 更新股票池行情与元数据
2. 运行多 expert 推理与 ensemble 聚合
3. 生成两套策略的 `risk_positions.csv`
4. 产出研究简报

## 推荐入口

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\invoke_daily_research_pipeline.ps1
```

调试时可跳过时间窗判断：

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\invoke_daily_research_pipeline.ps1 -IgnoreTimeWindow
```

## 流水线主步骤（脚本内已固化）

1. `fetch_stock_universe.py` 增量补齐 U.S. universe 行情（并写入 `latest` 稳定别名）
2. `fetch_stock_metadata.py` 更新元数据（按需）
3. 对两条策略分别运行 5 个 expert 推理
4. `predict_ensemble.py` 生成 ensemble 预测
5. `run_white_box_risk.py` 生成目标仓位与风险汇总
6. 输出 research phase operation brief

## 数据集约定（Alpaca）

- 全量初始化可从很早日期开始（例如 `1990-01-01`），实际可得范围以 Alpaca 返回为准。
- 日常夜间 research 默认走 `--incremental`，只补拉每个 symbol 缺失尾部日期。
- 下游统一读取 `data/interim/alpaca/universes/us_large_cap_30_latest_hfq_normalized.csv`，避免依赖带日期后缀的文件名。

## 关键输入

- 股票池：`configs/stock_universe_us_large_cap_30.txt`
- 策略：`execution/strategies/us_zeroshot_a_share_multi_expert_daily.json`
- 策略：`execution/strategies/us_full_multi_expert_daily.json`
- 预训练模型权重：`model_prediction/*/artifacts/validation_20260322/...`

## 关键输出

- `risk_management/white_box/runtime/us_zeroshot_a_share_multi_expert_daily/`
- `risk_management/white_box/runtime/us_full_multi_expert_daily/`
- `artifacts/ops_briefs/research/latest/`
