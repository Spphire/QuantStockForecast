# A股股票预测项目实验测试报告

## 1. 报告信息

- 报告生成日期：2026-03-21
- 项目目录：`C:\Users\Apricity\Desktop\股票`
- 报告范围：
  - `LightGBM` 预测层
  - `white_box_risk` 白盒风控层
  - 多组 A 股测试集曲线与加减仓行为分析

## 2. 实验目标

本轮实验的目标有三项：

1. 验证 `model_prediction -> white_box_risk -> backtest` 链路是否稳定可复现。
2. 比较不同预测任务和不同组合规则下的收益、超额收益、回撤和换手。
3. 分析组合行为究竟更像“整仓切换”，还是更像“逐步加仓/减仓”。

## 3. 数据与测试设置

### 3.1 数据来源

- 行情来源：`AKShare`
- 股票池文件：[stock_universe_large_cap_50.txt](C:/Users/Apricity/Desktop/股票/configs/stock_universe_large_cap_50.txt)
- 合并数据集：[large_cap_50_20200101_20241231_hfq_normalized.csv](C:/Users/Apricity/Desktop/股票/data/interim/akshare/universes/large_cap_50_20200101_20241231_hfq_normalized.csv)
- 行业元数据：[large_cap_50_metadata.csv](C:/Users/Apricity/Desktop/股票/data/interim/akshare/universes/large_cap_50_metadata.csv)

本次研究型主数据集实际覆盖 `64` 只股票。

### 3.2 建模任务

- `ranking`：预测未来 `5` 个交易日横截面超额收益排序
- `regression`：预测未来 `5` 个交易日收益率
- `classification`：预测未来 `5` 个交易日是否上涨

### 3.3 时间切分

#### Ranking

- 训练集：`2020-04-02` 到 `2023-07-28`
- 验证集：`2023-07-31` 到 `2024-04-17`
- 测试集：`2024-04-18` 到 `2024-12-31`

#### Regression

- 训练集：`2020-04-02` 到 `2023-07-24`
- 验证集：`2023-07-25` 到 `2024-04-10`
- 测试集：`2024-04-11` 到 `2024-12-24`

说明：

- 所有实验均使用按时间切分，而不是随机切分。
- 回测基于测试集预测结果开展。

### 3.4 统一风控设置

除特别说明外，多数实验使用以下约束：

- 持有周期：`5` 个交易日
- 调仓频率：每 `5` 个交易日
- 交易成本：`10 bps`
- 主行业约束：`industry_group` 每组最多 `1` 只
- 次级风格约束：`amount_bucket` 每组最多 `2` 只
- 最低价格：`5`
- 最低成交额：`1e8`

## 4. 模型层结果

### 4.1 Ranking 模型

来源：[metrics.json](C:/Users/Apricity/Desktop/股票/model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_ranking_5d/metrics.json)

- 股票数：`64`
- 测试集行数：`11072`
- `return_correlation = 0.0728`
- `top_decile_mean_return = 0.0158`
- `bottom_decile_mean_return = -0.0053`
- `top_bottom_spread = 0.0212`
- `best_iteration = 113`

解读：

- `ranking` 模型已经能在测试集上拉开上下分位收益差。
- 它更适合接横截面选股，而不是做单点涨跌判断。

### 4.2 Regression 模型

来源：[metrics.json](C:/Users/Apricity/Desktop/股票/model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/metrics.json)

- 股票数：`64`
- 测试集行数：`11072`
- `mae = 0.0370`
- `rmse = 0.0607`
- `correlation = 0.1089`
- `directional_accuracy = 0.4949`
- `best_iteration = 32`

解读：

- 回归相关性略高于 ranking 的 `return_correlation`，但方向准确率并不突出。
- 回归更依赖组合层是否能把弱信号变成有效仓位。

## 5. 白盒风控实验场景

实验脚本：[run_a_share_curve_suite.py](C:/Users/Apricity/Desktop/股票/risk_management/white_box/scripts/run_a_share_curve_suite.py)

输出目录：[a_share_curve_suite](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite)

本轮纳入比较的主要场景：

- `ranking_balanced`
- `ranking_smoothed`
- `regression_balanced`
- `regression_concentrated`
- `regression_equal`
- `regression_smoothed`
- `regression_smoothed_strict`

补充说明：

- `classification_guarded` 使用的是另一套较小股票池，结果保留作参考，但不建议与 `large_cap_50` 系列直接横向比较。

## 6. 收益结果总览

来源：[scenario_comparison.csv](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/scenario_comparison.csv)

| 场景 | 模式 | 总收益 | 基准收益 | 超额收益 | 最大回撤 | 平均换手 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `ranking_balanced` | ranking | 28.84% | 15.02% | 13.82% | -8.76% | 0.7030 |
| `ranking_smoothed` | ranking | 23.04% | 15.02% | 8.01% | -10.39% | 0.3765 |
| `regression_concentrated` | regression | 23.32% | 17.32% | 6.00% | -16.42% | 0.8024 |
| `regression_balanced` | regression | 22.42% | 17.32% | 5.10% | -17.44% | 0.7535 |
| `regression_equal` | regression | 21.85% | 17.32% | 4.53% | -15.42% | 0.7400 |
| `regression_smoothed_strict` | regression | 9.96% | 17.32% | -7.36% | -11.28% | 0.0624 |
| `regression_smoothed` | regression | 8.39% | 17.32% | -8.93% | -14.49% | 0.1296 |

核心观察：

- `ranking_balanced` 是当前主线上收益最好的实验。
- `ranking_smoothed` 在收益回落的情况下，显著降低了换手，更接近真实的“加减仓”逻辑。
- `regression` 两条平滑版本虽然压低了换手，但收益下降过多，暂时不适合作为主方案。

## 7. 曲线表现

- 净值曲线：[equity_curves.png](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/equity_curves.png)
- 回撤曲线：[drawdown_curves.png](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/drawdown_curves.png)

从曲线角度看：

- `ranking_balanced` 上行速度最快，但更偏向主动换仓。
- `ranking_smoothed` 曲线略慢，但调仓节奏更平滑。
- `regression_concentrated` 虽然总收益不低，但回撤显著高于 ranking 主线。

## 8. 加仓减仓行为分析

来源：[action_comparison.csv](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/action_comparison.csv)

### 8.1 Ranking Balanced

- `open = 122`
- `exit = 117`
- `add = 26`
- `reduce = 20`
- `hold = 2`

解读：

- 这条策略更像“换一批股票”，不是连续管理原有仓位。
- 收益强，但组合行为更激进。

### 8.2 Ranking Smoothed

- `open = 57`
- `exit = 15`
- `add = 178`
- `reduce = 158`
- `hold = 545`

来源：[risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/ranking_smoothed/risk_summary.json)

进一步指标：

- `mean_desired_turnover = 0.7325`
- `mean_turnover = 0.3765`
- `mean_turnover_reduction = 0.3561`
- `turnover_budget_binding_rate = 97.06%`

解读：

- 这条曲线已经明显从“整仓切换”转向“逐步加仓/减仓”。
- 平滑参数对换手的压制非常强，大多数调仓期都触发了换手预算约束。
- 它是当前最接近真实组合管理习惯的一条实验曲线。

### 8.3 Regression Balanced

- `open = 131`
- `exit = 126`
- `add = 21`
- `reduce = 21`
- `hold = 1`

解读：

- 回归基线在行为上依然偏“整仓切换”。
- 虽然有超额收益，但组合层还没有把它变成足够平滑的加减仓系统。

### 8.4 Regression Smoothed

- `open = 42`
- `exit = 0`
- `add = 69`
- `reduce = 96`
- `hold = 819`

解读：

- 从行为模式上看，平滑规则已经生效。
- 但收益显著恶化，说明当前回归信号强度还不够支撑这种缓慢调仓方式。

## 9. 代表性结论

### 9.1 当前最强收益方案

`ranking_balanced`

- 优点：收益最高、超额最高、回撤控制也不错。
- 缺点：更像“高频换仓”，不够像真实组合经理的加减仓行为。

### 9.2 当前最优平滑调仓方案

`ranking_smoothed`

- 优点：明显减少开仓/清仓次数，增加加仓/减仓与持有动作，行为模式更合理。
- 缺点：收益比 `ranking_balanced` 下降约 `5.8` 个百分点，总回撤略有变差。

### 9.3 当前不建议作为主线的方案

`regression_smoothed` 与 `regression_smoothed_strict`

- 原因：虽然换手被显著压低，但超额收益转负，说明当前回归信号不足以支持强约束的平滑调仓。

## 10. 实验结论

本轮实验可以得到三个明确结论：

1. 项目的工程链路已经完整打通，能够稳定完成 `预测 -> 风控 -> 回测 -> 曲线 -> 动作统计`。
2. 在当前数据和特征下，`ranking` 路线比 `regression` 更适合做 A 股横截面选股主线。
3. 如果目标是“更像真实投资组合管理”，则应继续沿着 `ranking_smoothed` 方向优化，而不是继续强化回归平滑版本。

## 11. 下一步建议

推荐按下面顺序推进：

1. 以 `ranking_smoothed` 为主线，继续调 `hold_buffer / max_turnover / min_trade_weight`。
2. 加入市场状态控制，例如强势市允许更高换手、弱势市自动降仓。
3. 增加更真实的交易约束，例如涨跌停、停牌、成交额分层、仓位下限。
4. 扩展更多股票池和更长测试区间，验证结论是否稳定。

## 12. 附件与结果文件

- 场景总表：[scenario_comparison.csv](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/scenario_comparison.csv)
- 动作统计：[action_comparison.csv](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/action_comparison.csv)
- 曲线长表：[curve_comparison_long.csv](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/curve_comparison_long.csv)
- 宽表曲线：[equity_curve_wide.csv](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/equity_curve_wide.csv)
- ranking 平滑动作明细：[risk_actions.csv](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/ranking_smoothed/risk_actions.csv)
- ranking 平滑摘要：[risk_summary.json](C:/Users/Apricity/Desktop/股票/risk_management/white_box/experiments/a_share_curve_suite/ranking_smoothed/risk_summary.json)
