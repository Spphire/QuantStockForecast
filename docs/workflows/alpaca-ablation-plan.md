# 工作流：Ablation 实验计划（A 股 vs A 股+美股，单 Expert vs Multi-Expert Voting）

## 1. 实验目标

本计划用于一次可复现、可审计的系统性 ablation：

1. 数据集 ablation：
   - `D1`：仅 A 股数据
   - `D2`：A 股 + 美股全量（项目内全历史可用数据）
2. Expert ablation：
   - `E1`：白盒风控 + LightGBM
   - `E2`：白盒风控 + XGBoost
   - `E3`：白盒风控 + CatBoost
   - `E4`：白盒风控 + LSTM
   - `E5`：白盒风控 + Transformer
   - `E6`：白盒风控 + Multi-Expert Voting（5 expert 合票）
3. 每个组合都要：
   - 重新训练
   - 完整推理
   - 白盒风控
   - Alpaca 风格执行回放
   - 与 `SPY` 基准比较收益

总实验规模：`2 datasets x 6 strategies = 12` 组主实验。

## 2. 固定实验约束（必须一致）

### 2.1 数据切分与 Walk-Forward 规则

- 按时间切分（unique date）：
  - 训练集：前 `70%`
  - 验证集：中间 `15%`
  - 测试集：后 `15%`
- 训练脚本统一参数：
  - `--train-ratio 0.7`
  - `--valid-ratio 0.15`
- 测试评估必须使用 `walk-forward`（禁止一次性静态测试替代）：
  - 滚动范围：最后 `15%` 测试区间
  - 任意测试日期 `t` 的特征与归一化仅可使用 `<= t-1` 的历史信息
  - 建议采用 expanding window（历史窗口只扩不缩），按日或按周滚动
  - 每个滚动步输出一个 `session`，最终聚合为总 summary
- 已启用 label horizon purge（防边界泄露），不可关闭。

### 2.2 训练任务统一参数

- 默认统一模式：`regression`
- 默认预测周期：`horizon=5d`
- 固定随机种子：`seed=42`（支持 seed 的模型必须显式传入）
- 所有模型输出都放在单独实验目录，禁止覆盖线上主线 artifacts。

### 2.3 风控与执行统一参数

- 风控：同一套 `run_white_box_risk.py` 参数（仅输入 predictions 不同）
- 执行：统一使用 `execution/scripts/backtest_alpaca_style.py`
- 初始权益统一：`100000`
- 交易成本统一：`10 bps`（若策略配置不同，以实验参数覆盖）

### 2.4 评估域统一（关键）

- 为了与 `SPY` 做同口径比较，执行评估域固定为美股 Alpaca universe。
- `D1/D2` 差异主要体现在训练数据来源，执行评估输入统一为：
  - `data/interim/alpaca/universes/us_large_cap_30_latest_hfq_normalized.csv`

### 2.5 基准与比较口径统一（强制）

- `benchmark_total_return` 必须来自真实 `SPY buy&hold`，禁止使用“截面均值收益”替代。
- 若预测集不含 `SPY`，必须走“外部基准序列”流程（例如单独拉取 `SPY` 日线），再并入汇总表。
- 12 组横向排名前，必须先统一比较区间与 session mask：
  - 比较区间：`window_start = max(all_run_start)`，`window_end = min(all_run_end)`
  - 会话掩码：统一使用同一 `SPY` 交易日历（固定 calendar）
  - 对于缺失会话，策略权益使用“持仓延续/权益前值延续”方式对齐，禁止直接丢弃该会话
- 若统一后可比会话数过少（建议 `<120`），必须在报告中标红并禁止给出“最终优胜策略”结论。

## 3. 数据集定义

### 3.1 D1：仅 A 股

- 输入：
  - `data/interim/akshare/universes/large_cap_50_20200101_20241231_hfq_normalized.csv`

### 3.2 D2：A 股 + 美股全量

- 输入：
  - A 股：`data/interim/akshare/universes/large_cap_50_20200101_20241231_hfq_normalized.csv`
  - 美股：`data/interim/alpaca/universes/us_large_cap_30_19900101_20260322_hfq_normalized.csv`
- 合并产物（建议）：
  - `data/interim/experiments/ablation/a_share_plus_us_full_19900101_20260322_hfq_normalized.csv`
- 注：此处“美股全量”指项目当前主线可用的美股全历史数据（`us_large_cap_30`），非全市场全部股票。

### 3.3 合并数据生成（一次性）

```powershell
@'
from pathlib import Path
import pandas as pd

root = Path(r"C:\Users\Apricity\Desktop\QuantStockForecast")
a_path = root / "data/interim/akshare/universes/large_cap_50_20200101_20241231_hfq_normalized.csv"
u_path = root / "data/interim/alpaca/universes/us_large_cap_30_19900101_20260322_hfq_normalized.csv"
out_path = root / "data/interim/experiments/ablation/a_share_plus_us_full_19900101_20260322_hfq_normalized.csv"
out_path.parent.mkdir(parents=True, exist_ok=True)

a = pd.read_csv(a_path, encoding="utf-8-sig")
u = pd.read_csv(u_path, encoding="utf-8-sig")
a["market_tag"] = "CN"
u["market_tag"] = "US"

all_cols = sorted(set(a.columns) | set(u.columns))
for c in all_cols:
    if c not in a.columns:
        a[c] = pd.NA
    if c not in u.columns:
        u[c] = pd.NA

merged = pd.concat([a[all_cols], u[all_cols]], ignore_index=True)
merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
merged = merged.dropna(subset=["date"]).sort_values(["symbol", "date"], kind="stable")
merged["date"] = merged["date"].dt.strftime("%Y-%m-%d")
merged.to_csv(out_path, index=False, encoding="utf-8")
print(out_path)
'@ | python -
```

### 3.4 数据参数与来源模板（每次实验必须落表）

请在每轮实验开始前，把以下参数完整记录到实验报告或运行清单：

| 字段 | D1（仅 A 股训练） | D2（A 股+美股训练） | 说明 |
|---|---|---|---|
| `a_share_dataset_path` | 必填 | 必填 | A 股训练数据文件绝对/相对路径 |
| `a_share_date_start` | 必填 | 必填 | A 股数据起始日期（YYYY-MM-DD） |
| `a_share_date_end` | 必填 | 必填 | A 股数据结束日期（YYYY-MM-DD） |
| `a_share_symbols_file` | 必填 | 必填 | A 股股票池文件 |
| `a_share_symbol_count` | 必填 | 必填 | 本次冻结的 A 股股票池数量 |
| `a_share_price_provider` | 必填 | 必填 | A 股价格 provider（例如 `akshare`） |
| `a_share_price_source` | 必填 | 必填 | A 股价格上游接口（例如 `stock_zh_a_hist`） |
| `a_share_download_origin` | 必填 | 必填 | A 股真实下载来源（例如 Eastmoney/Sina，经 AkShare 调用） |
| `a_share_adjust` | 必填 | 必填 | A 股复权参数（例如 `hfq`） |
| `a_share_metadata_provider` | 可选 | 可选 | A 股元数据 provider（例如 `akshare`） |
| `a_share_metadata_source` | 可选 | 可选 | A 股元数据上游接口（例如 `stock_industry_change_cninfo`） |
| `a_share_metadata_download_origin` | 可选 | 可选 | A 股元数据真实下载来源（例如 CNINFO，经 AkShare 调用） |
| `us_dataset_path` | 空 | 必填 | 美股训练数据文件路径 |
| `us_date_start` | 空 | 必填 | 美股数据起始日期（YYYY-MM-DD） |
| `us_date_end` | 空 | 必填 | 美股数据结束日期（YYYY-MM-DD） |
| `us_symbols_file` | 空 | 必填 | 美股股票池文件 |
| `us_symbol_count` | 空 | 必填 | 本次冻结的美股股票池数量 |
| `us_price_provider` | 空 | 必填 | 美股价格 provider（例如 `alpaca`） |
| `us_price_source` | 空 | 必填 | 美股价格上游接口（例如 Alpaca `/v2/stocks/bars`） |
| `us_download_origin` | 空 | 必填 | 美股真实下载来源（Alpaca 数据域名/API） |
| `us_alpaca_feed` | 空 | 必填 | Alpaca feed（`iex` 或 `sip`） |
| `us_alpaca_adjustment` | 空 | 必填 | Alpaca API adjustment 参数（当前 `raw`） |
| `us_metadata_provider` | 空 | 必填 | 美股元数据 provider（例如 `wikipedia_sp500`） |
| `us_metadata_source` | 空 | 必填 | 美股元数据来源（Wikipedia S&P 500 表） |
| `us_metadata_download_origin` | 空 | 必填 | 美股元数据真实下载 URL |
| `eval_universe_path` | 必填 | 必填 | 统一评估输入数据 |
| `eval_start` | 必填 | 必填 | 评估起始日期（建议 2024-01-01） |
| `eval_end` | 必填 | 必填 | 评估结束日期（建议运行当日） |
| `benchmark_symbol` | 必填 | 必填 | 本实验固定为 `SPY` |
| `source_manifest_path` | 必填 | 必填 | 本轮实际使用的数据 manifest 路径 |
| `source_fetched_at` | 必填 | 必填 | 本轮数据抓取时间戳（本机时区） |

建议在每次实验目录新增一个 `dataset_params.json`，按上述字段冻结参数，避免“同名实验、参数不同”。

### 3.5 本次实验建议冻结参数（当前仓库快照）

#### A 股参数

- `a_share_dataset_path`:
  - `data/interim/akshare/universes/large_cap_50_20200101_20241231_hfq_normalized.csv`
- `a_share_date_start`: `2020-01-01`
- `a_share_date_end`: `2024-12-31`
- `a_share_symbols_file`:
  - `configs/stock_universe_large_cap_50.txt`
- `a_share_symbol_count`（当前文件实际行数）: `64`
- `a_share_price_provider`: `akshare`（落盘 manifest 中常见 `akshare-eastmoney` / `akshare-sina`）
- `a_share_price_source`: `ak.stock_zh_a_hist`（Eastmoney）失败时回退 `ak.stock_zh_a_daily`（Sina）
- `a_share_download_origin`: Eastmoney / Sina（日线均由 AkShare 发起在线下载，不以本地缓存作为数据源）
- `a_share_adjust`: `hfq`
- `a_share_metadata_provider`: `akshare`
- `a_share_metadata_source`: `ak.stock_industry_change_cninfo`
- `a_share_metadata_download_origin`: CNINFO（经 AkShare 下载）

#### 美股参数（用于 D2 训练）

- `us_dataset_path`:
  - `data/interim/alpaca/universes/us_large_cap_30_19900101_20260322_hfq_normalized.csv`
- `us_date_start`: `1990-01-01`
- `us_date_end`: `2026-03-22`（应随最新拉取更新）
- `us_symbols_file`:
  - `configs/stock_universe_us_large_cap_30.txt`
- `us_symbol_count`: `30`
- `us_price_provider`: `alpaca`
- `us_price_source`: Alpaca Market Data API `GET /v2/stocks/bars`（`timeframe=1Day`）
- `us_download_origin`: `https://data.alpaca.markets/v2/stocks/bars`
- `us_alpaca_feed`: `iex`
- `us_alpaca_adjustment`: `raw`
- `us_metadata_provider`: `wikipedia_sp500`
- `us_metadata_source`: `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`
- `us_metadata_download_origin`: `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`

#### 统一评估参数（D1/D2 同口径）

- `eval_universe_path`:
  - `data/interim/alpaca/universes/us_large_cap_30_latest_hfq_normalized.csv`
- `eval_start`: `2024-01-01`
- `eval_end`: `2026-03-22`（建议每次实验写成实际运行日期）
- `benchmark_symbol`: `SPY`
- `source_manifest_path`（示例）:
  - `data/interim/alpaca/universes/us_large_cap_30_latest_hfq_manifest.json`
- `source_fetched_at`: 建议记录 nightly/research 拉取完成时间（例如 `2026-03-22 21:35:00`，本机时区）

#### 当前股票池快照（用于复盘）

`configs/stock_universe_us_large_cap_30.txt`:

`AAPL, MSFT, NVDA, AMZN, GOOGL, META, AVGO, JPM, V, TSLA, WMT, XOM, MA, PG, COST, NFLX, JNJ, ORCL, HD, BAC, ABBV, KO, CRM, CSCO, AMD, MRK, UNH, CVX, LIN, MCD`

`configs/stock_universe_large_cap_50.txt`（当前快照共 64 只）:

`000001, 000002, 000063, 000100, 000157, 000166, 000333, 000338, 000425, 000538, 000568, 000596, 000625, 000651, 000725, 000768, 000776, 000858, 002027, 002142, 002230, 002304, 002415, 002594, 300014, 300015, 300059, 300124, 300274, 300750, 600000, 600009, 600016, 600028, 600030, 600031, 600036, 600050, 600104, 600111, 600276, 600309, 600519, 600690, 600809, 601012, 601066, 601088, 601166, 601288, 601318, 601398, 601601, 601628, 601668, 601688, 601728, 601857, 601888, 601899, 601919, 601939, 601985, 601988`

### 3.6 数据来源清单（价格/元数据/股票池）

| 维度 | A 股（D1/D2 训练部分） | 美股（D2 训练 + D1/D2 统一评估） |
|---|---|---|
| 下载来源（非本地缓存） | Eastmoney/Sina（由 AkShare 在线下载） | Alpaca Market Data API（在线下载） |
| 价格抓取脚本 | `data_module/fetchers/scripts/fetch_stock_universe.py --provider akshare` | `data_module/fetchers/scripts/fetch_stock_universe.py --provider alpaca` |
| 价格上游来源 | AkShare：主接口 `stock_zh_a_hist`，失败回退 `stock_zh_a_daily` | Alpaca Market Data：`GET /v2/stocks/bars` |
| 下载入口（可审计） | AkShare SDK 调用日志 + universe manifest | `https://data.alpaca.markets/v2/stocks/bars` + universe manifest |
| 关键参数 | `adjust=hfq` | `timeframe=1Day`, `feed=iex`, `adjustment=raw` |
| 元数据抓取脚本 | `data_module/fetchers/scripts/fetch_stock_metadata.py --provider akshare` | `data_module/fetchers/scripts/fetch_stock_metadata.py --provider wikipedia_sp500` |
| 元数据上游来源 | AkShare CNINFO 行业变更接口 `stock_industry_change_cninfo` | Wikipedia `List_of_S%26P_500_companies`（GICS） |
| 元数据下载入口（可审计） | CNINFO（经 AkShare） | `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies` |
| 股票池文件 | `configs/stock_universe_large_cap_50.txt`（当前 64 只） | `configs/stock_universe_us_large_cap_30.txt`（30 只） |
| 标准化输出目录 | `data/interim/akshare/universes/` | `data/interim/alpaca/universes/` |

建议把每轮实际用到的 `*_manifest.json` 与 `dataset_params.json` 一并归档到实验目录，作为复盘审计依据。

## 4. 实验矩阵与命名规范

### 4.1 运行 ID

- `D1_E1_lightgbm`
- `D1_E2_xgboost`
- `D1_E3_catboost`
- `D1_E4_lstm`
- `D1_E5_transformer`
- `D1_E6_ensemble_vote`
- `D2_E1_lightgbm`
- `D2_E2_xgboost`
- `D2_E3_catboost`
- `D2_E4_lstm`
- `D2_E5_transformer`
- `D2_E6_ensemble_vote`

### 4.2 目录规范（建议）

- 根目录：`artifacts/experiments/alpaca_ablation_YYYYMMDD/`
- 子目录：
  - `train/<dataset>/<expert>/`
  - `predict/<dataset>/<expert>/`
  - `risk/<dataset>/<strategy>/`
  - `execution/<dataset>/<strategy>/`
  - `report/`

## 5. 执行步骤（逐步）

### 5.1 训练 5 个基础 expert（每个 dataset 各 5 次）

统一入口：

```powershell
python model_prediction/common/run_expert_model.py train <expert> -- <input_csv> --mode regression --horizon 5 --train-ratio 0.7 --valid-ratio 0.15 --output-dir <train_output_dir>
```

其中：

- `<expert>` in `lightgbm,xgboost,catboost,lstm,transformer`
- LSTM/Transformer 建议额外显式：
  - LSTM：`--seed 42`
  - Transformer：`--seed 42`

### 5.2 Walk-Forward 推理与会话构建（对齐 Alpaca 流程）

评估输入仍固定为：

- `data/interim/alpaca/universes/us_large_cap_30_latest_hfq_normalized.csv`

但执行方式改为 `walk-forward`：

1. 从最后 `15%` 测试区间生成按日期排序的 `session` 列表（建议日频）。
2. 对每个 `session_date=t`：
   - 仅使用 `<= t-1` 的历史样本进行训练/验证（含归一化与特征构建）
   - 仅对 `t` 这一天输出预测
   - 保存到 `predict/<dataset>/<expert>/sessions/<YYYY-MM-DD>/`
3. 会话级预测再进入白盒风控和执行回放，最终聚合 `sessions` 主汇总。

如果计算资源受限，可采用“周度重训 + 日度滚动预测”，但必须在报告里披露重训频率。

### 5.3 构建 Multi-Expert Voting

```powershell
python model_prediction/ensemble/scripts/predict_ensemble.py <lightgbm_pred_csv> `
  --prediction-csv <xgboost_pred_csv> `
  --prediction-csv <catboost_pred_csv> `
  --prediction-csv <lstm_pred_csv> `
  --prediction-csv <transformer_pred_csv> `
  --method vote `
  --min-experts 5 `
  --model-name ensemble_vote `
  --output-dir <predict_output_dir_for_vote>
```

### 5.4 白盒风控（单 expert + vote 都要跑）

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py <predictions_csv> `
  --metadata-csv data/interim/alpaca/universes/us_large_cap_30_metadata.csv `
  --rebalance-step 1 `
  --top-k 5 `
  --min-score 0 `
  --min-confidence 0.7 `
  --min-close 5 `
  --min-amount 100000000 `
  --group-column industry_group `
  --max-per-group 1 `
  --secondary-group-column amount_bucket `
  --secondary-max-per-group 2 `
  --weighting score_confidence `
  --max-position-weight 0.35 `
  --max-gross-exposure 0.85 `
  --confidence-target 0.90 `
  --min-gross-exposure 0.55 `
  --transaction-cost-bps 10 `
  --benchmark-symbol SPY `
  --output-dir <risk_output_dir>
```

### 5.5 Alpaca 风格执行回放

为每个策略生成一个临时 strategy config（`source.path` 指向对应 `risk_positions.csv`），然后执行：

```powershell
python execution/scripts/backtest_alpaca_style.py <strategy_config_json> `
  --universe-csv data/interim/alpaca/universes/us_large_cap_30_19900101_20260322_hfq_normalized.csv `
  --initial-equity 100000 `
  --output-dir <execution_output_dir>
```

## 6. SPY 对比的硬性校验

为了保证 `benchmark_symbol=SPY` 真正生效，必须满足至少一条：

1. 预测输入数据中包含 `SPY`，且能进入 risk pipeline 的 `date_slice`。
2. 若当前 universe 不含 `SPY`，则单独计算 `SPY buy&hold` 基准并在汇总表里合并（禁止把“全体均值收益”当作 SPY）。

并增加以下阻断规则（必须通过）：

3. 若 risk/execution 汇总中的 benchmark 字段来自 fallback（例如 `cross_section_mean`），该 run 不得进入最终排名。
4. 最终排名必须基于“统一 SPY 日历 + 统一比较窗口”的重算指标（`comparable_excess_total_return`），而不是原始 run 内部 excess。

建议在实验前做阻断检查：

```powershell
Import-Csv <predictions_csv> | Where-Object { $_.symbol -eq "SPY" } | Select-Object -First 1
```

若为空，先补齐 SPY 基准流程，再继续实验。

## 7. 汇总指标（最终报告必须包含）

每个 run 必须输出一个主汇总（建议 `summary.json`），并包含以下 Primary 字段：

1. `sessions`
2. `total_return`
3. `annualized_return`
4. `annualized_volatility`
5. `sharpe`
6. `max_drawdown`
7. `benchmark_total_return`
8. `mean_turnover`
9. `mean_cost_bps`

并新增口径审计字段（用于可比性检查）：

10. `comparison_mask_start`
11. `comparison_mask_end`
12. `comparison_session_count`
13. `benchmark_source`（必须明确为 `SPY buy&hold`）

除主汇总外，建议保留模型层 `metrics.json`、风控层 `risk_summary.json`、执行层 `execution_summary.json` 作为审计明细。

## 8. 最终实验报告模板

报告建议产出到：

- `artifacts/experiments/alpaca_ablation_YYYYMMDD/report/ablation_report.md`

报告结构建议：

1. 实验设置（数据、模型、风控、执行、时间范围）
2. 12 组实验总表（按 `excess_total_return` 排序）
3. 分组对比：
   - D1 vs D2（同 expert 横向对比）
   - 单 expert vs ensemble vote（同 dataset 纵向对比）
4. 稳定性分析：
   - 回撤
   - 换手
   - 成交成本
5. 结论与下一步：
   - 哪个组合最优
   - 是否进入生产候选
   - 后续要补的实验

## 9. 运行安全与回滚要求

1. 全部输出写入 `artifacts/experiments/...`，禁止覆盖主线运行目录。
2. 不改现有调度任务，不改现有生产策略 JSON。
3. 单个 run 失败不影响整体，记录失败原因并继续。
4. 实验完成后只提交：
   - 实验报告
   - 汇总 CSV/JSON
   - 必要脚本（若有）
