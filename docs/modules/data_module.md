# 模块说明：data_module

## 职责

`data_module` 负责把外部行情与元数据转换成统一 schema，供预测层直接消费。

## 关键入口

- `data_module/fetchers/scripts/fetch_stock_history.py`
  - 单标的抓取（`demo/akshare/stooq/alpaca`）
- `data_module/fetchers/scripts/fetch_stock_universe.py`
  - 多标的批量抓取并合并
- `data_module/fetchers/scripts/fetch_stock_metadata.py`
  - 行业/公司元数据抓取（A 股或 S&P500）
- `data_module/fetchers/scripts/normalize_ohlcv.py`
  - 任意 CSV 头部映射到统一 schema

## 统一 schema

定义位置：`data_module/common/stock_schema.py`

- 必需列：`date, open, high, low, close, volume`
- 常用列：`symbol, amount, turnover, pct_change, price_change, amplitude`
- 处理逻辑：字段别名映射、数值化、日期标准化、按 `symbol/date` 排序

## 产物路径约定

- 原始数据：`data/raw/<provider>/..._raw.csv`
- 标准化数据：`data/interim/<provider>/..._normalized.csv`
- 清单文件：`..._manifest.json`
- 股票池合并文件：`data/interim/<provider>/universes/..._normalized.csv`
- 股票池稳定别名：`data/interim/<provider>/universes/<name>_latest_<adjust>_normalized.csv`

## 示例命令

首次全量初始化美股股票池（Alpaca）：

```powershell
python data_module/fetchers/scripts/fetch_stock_universe.py --provider alpaca --symbols-file configs/stock_universe_us_large_cap_30.txt --name us_large_cap_30 --start 1990-01-01 --end 2026-03-22 --alpaca-env-prefix ALPACA_ZERO_SHOT --alpaca-feed iex --write-latest-alias --continue-on-error
```

夜间任务增量补齐（基于已存在数据集）：

```powershell
python data_module/fetchers/scripts/fetch_stock_universe.py --provider alpaca --symbols-file configs/stock_universe_us_large_cap_30.txt --name us_large_cap_30 --start 1990-01-01 --end 2026-03-22 --alpaca-env-prefix ALPACA_ZERO_SHOT --alpaca-feed iex --incremental --write-latest-alias --continue-on-error
```

抓取元数据：

```powershell
python data_module/fetchers/scripts/fetch_stock_metadata.py --provider wikipedia_sp500 --symbols-file configs/stock_universe_us_large_cap_30.txt --output-csv data/interim/alpaca/universes/us_large_cap_30_metadata.csv
```
