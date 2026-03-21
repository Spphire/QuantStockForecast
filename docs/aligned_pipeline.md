# 对齐后的 LightGBM 基线流程

这套流程的目标是让 `data_module/fetchers` 产出的标准化 CSV 可以直接被 `model_prediction/lightgbm` 消费。

## 统一数据契约

标准化后的核心字段如下：

- `date`
- `symbol`
- `open`
- `high`
- `low`
- `close`
- `volume`

可选字段包括：

- `amount`
- `turnover`
- `pct_change`
- `price_change`
- `amplitude`
- `provider`
- `adjust`

## 先跑通一条无依赖链路

先用 demo 数据验证流程是否对齐：

```powershell
python data_module/fetchers/scripts/fetch_stock_history.py --provider demo --symbol 000001 --start 2023-01-01 --end 2024-12-31
python model_prediction/lightgbm/scripts/check_stock_dataset.py data/interim/demo/000001_20230101_20241231_normalized.csv
python model_prediction/lightgbm/scripts/train_lightgbm.py data/interim/demo/000001_20230101_20241231_normalized.csv --prepare-only
```

这一步不依赖 `lightgbm` 或 `akshare`，主要用来验证：

- fetcher 输出的列名是否符合统一 schema
- LightGBM 侧能否正常做特征和标签构造
- 时间切分是否能够成功

## 使用真实 A 股历史数据

安装依赖后，可以切到 `akshare` 数据源：

```powershell
python data_module/fetchers/scripts/fetch_stock_history.py --provider akshare --symbol 000001 --start 2020-01-01 --end 2024-12-31 --adjust hfq
python model_prediction/lightgbm/scripts/train_lightgbm.py data/interim/akshare/000001_20200101_20241231_hfq_normalized.csv --mode classification --horizon 5
```

说明：

- 当前抓数脚本会优先尝试 `AKShare + Eastmoney`
- 如果 Eastmoney 不稳定，会自动 fallback 到 `AKShare + 新浪日线`
- `manifest.json` 和标准化结果中的 `provider` 字段会保留实际使用的来源

## 使用多股票训练集

可以先准备一个股票池文件，例如：

`configs/stock_universe_large_cap.txt`

或者使用更大的示例股票池：

`configs/stock_universe_large_cap_50.txt`

然后批量抓取并合并成一个 universe 数据集：

```powershell
python data_module/fetchers/scripts/fetch_stock_universe.py --provider akshare --symbols-file configs/stock_universe_large_cap.txt --name large_cap --start 2020-01-01 --end 2024-12-31 --adjust hfq --continue-on-error
python model_prediction/lightgbm/scripts/check_stock_dataset.py data/interim/akshare/universes/large_cap_20200101_20241231_hfq_normalized.csv
python model_prediction/lightgbm/scripts/train_lightgbm.py data/interim/akshare/universes/large_cap_20200101_20241231_hfq_normalized.csv --mode classification --horizon 5
```

更推荐的研究型跑法是：

```powershell
python data_module/fetchers/scripts/fetch_stock_universe.py --provider akshare --symbols-file configs/stock_universe_large_cap_50.txt --name large_cap_50 --start 2020-01-01 --end 2024-12-31 --adjust hfq --continue-on-error
python model_prediction/lightgbm/scripts/train_lightgbm.py data/interim/akshare/universes/large_cap_50_20200101_20241231_hfq_normalized.csv --mode regression --horizon 5
```

这条路径更适合做横截面选股，因为模型直接学习未来收益率。

批量抓取会输出：

- 每支股票各自的 `raw/normalized/manifest`
- 一个合并后的 universe 数据集
- 一个 universe 级别的 manifest

## 使用 top-k 回测

训练完成后，可以直接对测试集预测结果做一个简单的 cross-sectional top-k 回测：

```powershell
python model_prediction/lightgbm/scripts/backtest_topk.py model_prediction/lightgbm/artifacts/large_cap_20200101_20241231_hfq_normalized_classification_5d/test_predictions.csv --top-k 3 --rebalance-step 5
```

如果是收益率回归模型，建议直接对 `pred_return` 做排序，并加入交易成本：

```powershell
python model_prediction/lightgbm/scripts/backtest_topk.py model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/test_predictions.csv --top-k 5 --rebalance-step 5 --score-column pred_return --min-score 0 --transaction-cost-bps 10
```

## 行业/风格中性化

可以先为股票池抓取行业元数据：

```powershell
python data_module/fetchers/scripts/fetch_stock_metadata.py --symbols-file configs/stock_universe_large_cap_50.txt --output-csv data/interim/akshare/universes/large_cap_50_metadata.csv
```

然后在回测阶段加行业和风格约束。例如：

```powershell
python model_prediction/lightgbm/scripts/backtest_topk.py model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/test_predictions.csv --top-k 5 --rebalance-step 5 --score-column pred_return --min-score 0 --transaction-cost-bps 10 --min-close 5 --min-amount 100000000 --metadata-csv data/interim/akshare/universes/large_cap_50_metadata.csv --group-column industry_group --max-per-group 1 --secondary-group-column amount_bucket --secondary-max-per-group 2
```

这组参数的含义是：

- 每次换仓最多选 5 只
- 同一个行业大类最多 1 只
- 同一个流动性分桶最多 2 只
- 过滤低价股和低成交额股票

这个回测脚本会：

- 每个换仓日按预测分数从高到低排序
- 选择 top-k 股票
- 使用预测文件里的真实未来收益列做持有期收益计算
- 输出收益、超额收益、回撤和胜率

## 使用白盒风控模块

如果你希望把模型输出和组合决策解耦，可以把 `test_predictions.csv` 交给 `risk_management/white_box`。

推荐的回归版示例：

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/test_predictions.csv --metadata-csv data/interim/akshare/universes/large_cap_50_metadata.csv --top-k 5 --min-score 0 --min-confidence 0.7 --min-close 5 --min-amount 100000000 --group-column industry_group --max-per-group 1 --secondary-group-column amount_bucket --secondary-max-per-group 2 --weighting score_confidence --max-position-weight 0.35 --transaction-cost-bps 10
```

如果你想让组合更像“逐步加减仓”，可以加上：

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_ranking_5d/test_predictions.csv --metadata-csv data/interim/akshare/universes/large_cap_50_metadata.csv --top-k 5 --min-confidence 0.7 --min-close 5 --min-amount 100000000 --group-column industry_group --max-per-group 1 --secondary-group-column amount_bucket --secondary-max-per-group 2 --weighting confidence --max-position-weight 0.35 --transaction-cost-bps 10 --hold-buffer 0.03 --max-turnover 0.5 --min-trade-weight 0.02
```

这三个参数的作用是：

- `hold-buffer`：给旧持仓一个保留缓冲
- `max-turnover`：限制每期换手幅度
- `min-trade-weight`：过滤很小的仓位变动

如果是 ranking 模型，也可以直接复用同一个入口：

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_ranking_5d/test_predictions.csv --metadata-csv data/interim/akshare/universes/large_cap_50_metadata.csv --top-k 5 --min-confidence 0.7 --min-close 5 --min-amount 100000000 --group-column industry_group --max-per-group 1 --secondary-group-column amount_bucket --secondary-max-per-group 2 --weighting confidence --max-position-weight 0.35 --transaction-cost-bps 10
```

这层会自动把不同模型的预测文件归一化成统一信号格式：

- `date`
- `symbol`
- `score`
- `confidence`
- `horizon`
- `model_name`

然后再执行：

- 信号过滤
- 流动性过滤
- 行业/风格分组限额
- 仓位分配
- 换手与交易成本扣减

输出文件包括：

- `risk_periods.csv`
- `risk_positions.csv`
- `risk_actions.csv`
- `risk_summary.json`

如果你想一次比较多条 A 股测试曲线，可以直接跑批量实验：

```powershell
python risk_management/white_box/scripts/run_a_share_curve_suite.py
```

这个脚本会汇总输出：

- `scenario_comparison.csv`
- `curve_comparison_long.csv`
- `equity_curve_wide.csv`
- `action_comparison.csv`
- `equity_curves.png`
- `drawdown_curves.png`

其中 `action_comparison.csv` 可以直接用来观察不同策略是在频繁整仓切换，还是更多通过加仓/减仓做动态调整。

## 美股 Zero-Shot 流程

当前系统也已经验证了从 A 股主线直接 zero-shot 到美股的流程：

```powershell
python data_module/fetchers/scripts/fetch_stock_universe.py --provider stooq --symbols-file configs/stock_universe_us_large_cap_30.txt --name us_large_cap_30 --start 2020-01-01 --end 2025-12-31 --continue-on-error
python data_module/fetchers/scripts/fetch_stock_metadata.py --provider wikipedia_sp500 --symbols-file configs/stock_universe_us_large_cap_30.txt --output-csv data/interim/stooq/universes/us_large_cap_30_metadata.csv
python model_prediction/lightgbm/scripts/predict_lightgbm.py data/interim/stooq/universes/us_large_cap_30_20200101_20251231_hfq_normalized.csv --model-path model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/model.txt --reference-metrics model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/metrics.json --output-dir model_prediction/lightgbm/artifacts/us_zeroshot_regression --eval-start 2024-01-01 --eval-end 2025-12-31
python model_prediction/lightgbm/scripts/predict_lightgbm.py data/interim/stooq/universes/us_large_cap_30_20200101_20251231_hfq_normalized.csv --model-path model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_ranking_5d/model.txt --reference-metrics model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_ranking_5d/metrics.json --output-dir model_prediction/lightgbm/artifacts/us_zeroshot_ranking --eval-start 2024-01-01 --eval-end 2025-12-31
python risk_management/white_box/scripts/run_us_zeroshot_suite.py
```

说明：

- `predict_lightgbm.py` 会按照 A 股训练时的特征列表重建美股输入
- 对当前美股里缺失的 `turnover` 相关特征，会使用中性值填充
- `run_us_zeroshot_suite.py` 会自动跑多组白盒风控场景并输出收益曲线、回撤曲线和动作统计

本轮真实实验说明：

- A 股训练的回归模型迁移到美股后，仍保留了一定可用性
- A 股训练的 ranking 模型迁移到美股后，当前表现较弱
- 这说明现有系统不仅能做 A 股主线，也具备了跨市场实验能力

## 执行层接入

如果你准备把研究结果推进到 paper trading，可以使用新的 `execution` 板块。

当前已经准备好的两条实战策略是：

- `execution/strategies/us_zeroshot_a_share_regression_concentrated.json`
- `execution/strategies/us_full_regression_balanced.json`

推荐先 dry-run：

```powershell
python execution/scripts/run_paper_strategy.py execution/strategies/us_zeroshot_a_share_regression_concentrated.json
python execution/scripts/run_paper_strategy.py execution/strategies/us_full_regression_balanced.json
python execution/scripts/compare_paper_strategies.py execution/strategies/us_zeroshot_a_share_regression_concentrated.json execution/strategies/us_full_regression_balanced.json
```

如果你已经配置好两个 Alpaca paper account，可以再切到提交模式：

```powershell
python execution/scripts/run_paper_strategy.py execution/strategies/us_zeroshot_a_share_regression_concentrated.json --submit
python execution/scripts/run_paper_strategy.py execution/strategies/us_full_regression_balanced.json --submit
```

执行层的默认输入是：

- 白盒风控产出的 `risk_positions.csv`

执行层会：

- 读取最新调仓日的目标仓位
- 做执行前白盒安全校验
- 对账当前持仓和目标仓位
- 生成 `order_intents.csv`
- 在 `--submit` 模式下通过 Alpaca REST 下单

## 训练产物

训练脚本会输出：

- `prepared_dataset.csv`
- `metrics.json`
- `test_predictions.csv`
- `feature_importance.csv`
- `model.txt`

回测脚本会额外输出：

- `backtest_periods.csv`
- `selected_trades.csv`
- `backtest_summary.json`

默认输出目录位于：

`model_prediction/lightgbm/artifacts/`

## 当前默认建模逻辑

默认特征包括：

- 日内收益
- 振幅比例
- 1/5/10 日收益率
- 20 日收益率
- 5/10/20 日均线偏离
- 60 日均线偏离
- 5/20 日成交量均值比
- 5/10/20 日波动率
- 20 日突破与价格位置
- 20 日成交量 z-score
- 市场相对收益
- 横截面分位特征
- 可选的成交额与换手率相关特征

默认标签包括：

- 分类任务：未来 N 日是否上涨
- 回归任务：未来 N 日收益率
