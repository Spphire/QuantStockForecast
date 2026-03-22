# White-Box Risk Management

`risk_management/white_box` 的目标是把模型预测层输出的信号，转成带约束的组合结果。

这层的设计原则是：

- 不直接耦合单个模型内部实现
- 统一消费 `model_prediction/common/signal_interface.py` 归一化后的信号
- 使用显式、可解释、可回测的规则做过滤、限仓和仓位控制
- 允许通过白盒参数把“整仓切换”逐步推向“加仓/减仓”

## 当前模块

- `signal_guard.py`
  对 `score/confidence/horizon` 做基础过滤
- `liquidity_rules.py`
  对价格、成交额、换手率、成交量做白名单过滤
- `exposure_rules.py`
  处理行业、风格和分桶约束
- `position_sizing.py`
  提供等权、按分数、按置信度等仓位分配方式
- `risk_pipeline.py`
  把信号过滤、选股、仓位和交易成本串成完整流程
- `scripts/run_white_box_risk.py`
  命令行入口
- `scripts/run_a_share_curve_suite.py`
  批量跑多组 A 股白盒风控场景，并导出曲线与动作对比
- `scripts/run_us_zeroshot_suite.py`
  批量跑多组美股 zero-shot 场景，并导出曲线与动作对比

## 输入接口

默认输入是模型产出的 `test_predictions.csv`。

只要预测文件里至少包含这些字段，风控层就可以接入：

- `date`
- `symbol`
- 一个模型分数字段
- 一个真实未来收益字段 `target_return_*d`

目前已经验证过三种输入：

- `classification`：`pred_probability`
- `regression`：`pred_return`
- `ranking`：`pred_score`

## 示例

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/test_predictions.csv --metadata-csv data/interim/akshare/universes/large_cap_50_metadata.csv --top-k 5 --min-score 0 --min-confidence 0.7 --min-close 5 --min-amount 100000000 --group-column industry_group --max-per-group 1 --secondary-group-column amount_bucket --secondary-max-per-group 2 --weighting score_confidence --max-position-weight 0.35 --transaction-cost-bps 10
```

如果你想做更平滑的加减仓，可以额外加这三个参数：

- `--hold-buffer`
  给原持仓一个分数缓冲带，避免轻微劣化就被立刻换掉
- `--max-turnover`
  限制每次调仓的最大换手
- `--min-trade-weight`
  忽略非常小的仓位变化，减少碎片化调仓

## 严格对齐设置（Peer Comparison）

如果你要对齐 `StockMachine-20260321` 的 `P0 Strict` 对照协议，可以直接用：

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py <predictions_csv> --metadata-csv <metadata_csv> --strict-peer-comparison
```

这个开关会一次性应用以下关键参数：

- `top_k=10`
- `min_close=10`
- `min_median_dollar_volume_20=50000000`
- `max_vol_20=0.04`
- `group_column=industry_sector` 且 `max_per_group=2`
- `sector_neutralization=true` 且 `sector_column=industry_sector`
- `transaction_cost_bps=10`
- `benchmark_symbol=SPY`
- `rebalance_step=5`

协议定义代码在：

- `risk_management/white_box/protocols.py`

## 输出

默认输出到预测文件同级目录下的 `white_box_risk/`：

- `risk_periods.csv`
- `risk_positions.csv`
- `risk_actions.csv`
- `risk_summary.json`

这三份文件分别用于：

- 看每期收益、换手、成本和净值
- 看每个调仓日实际选中的股票与仓位
- 看每次调仓是在开仓、加仓、减仓、持有还是清仓
- 看总收益、超额、回撤和年化表现

## 批量曲线实验

如果你想同时比较多条 A 股测试曲线，可以运行：

```powershell
python risk_management/white_box/scripts/run_a_share_curve_suite.py
```

这个脚本会输出：

- `scenario_comparison.csv`
- `curve_comparison_long.csv`
- `equity_curve_wide.csv`
- `action_comparison.csv`
- `equity_curves.png`
- `drawdown_curves.png`

适合用来比较不同模型输出、不同仓位规则和不同过滤强度下的收益与加减仓行为。

如果你想复现本次美股 zero-shot 实验，可以运行：

```powershell
python risk_management/white_box/scripts/run_us_zeroshot_suite.py
```

这个脚本默认会对以下产物做批量回测：

- `model_prediction/lightgbm/artifacts/us_zeroshot_regression/test_predictions.csv`
- `model_prediction/lightgbm/artifacts/us_zeroshot_ranking/test_predictions.csv`
- `data/interim/stooq/universes/us_large_cap_30_metadata.csv`

默认场景包括：

- `regression_balanced`
- `regression_concentrated`
- `ranking_balanced`
- `ranking_smoothed`

输出目录为：

- `risk_management/white_box/experiments/us_zeroshot_suite/`

## 当前模块定位

这层已经不再只是一个“回测脚本集合”，而是项目当前真正可用的 **组合与白盒风险规则核心**。  
如果后面继续扩展，我建议仍然保持这个模块的设计原则：

- 规则尽量显式
- 接口尽量稳定
- 风控尽量独立于具体模型实现
