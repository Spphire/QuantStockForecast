# 模块说明：risk_management

## 职责

`risk_management/white_box` 将预测信号转换成可执行组合，并输出回测统计与调仓动作。

## 核心入口

- `risk_management/white_box/scripts/run_white_box_risk.py`
- `risk_management/white_box/risk_pipeline.py`
- `risk_management/white_box/protocols.py`（严格对齐协议）

## 信号输入

风控入口消费 `test_predictions.csv`，并经 `model_prediction/common/signal_interface.py` 统一字段后处理。

关键字段包括：

- `date, symbol, score, confidence, horizon, model_name, model_mode`
- 可选流动性/行业字段：`close, amount, turnover, volume, industry_*`

## 风控输出

- `risk_periods.csv`：每次调仓收益/换手/暴露统计
- `risk_positions.csv`：目标仓位
- `risk_actions.csv`：开仓/加仓/减仓/平仓动作
- `risk_summary.json`：整体汇总指标

## 常用模式

### 1) 严格对齐模式（推荐用于 peer comparison）

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py <predictions_csv> --metadata-csv <metadata_csv> --strict-peer-comparison
```

### 2) 自定义参数模式（生产/研究）

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py <predictions_csv> --metadata-csv <metadata_csv> --top-k 5 --min-confidence 0.7 --group-column industry_group --max-per-group 1 --weighting score_confidence --max-position-weight 0.35 --max-gross-exposure 0.85 --transaction-cost-bps 10 --output-dir risk_management/white_box/runtime/<strategy_id>
```

