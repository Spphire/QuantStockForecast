# Fetchers

`data_module/fetchers` 是当前数据层里最成熟的模块，负责把真实数据源接进项目，并输出统一格式的数据文件。

## 当前脚本

- [fetch_stock_history.py](C:/Users/Apricity/Desktop/股票/data_module/fetchers/scripts/fetch_stock_history.py)
  拉取单支股票历史行情
- [fetch_stock_universe.py](C:/Users/Apricity/Desktop/股票/data_module/fetchers/scripts/fetch_stock_universe.py)
  拉取股票池并合并成 universe 数据集
  - 支持 `--incremental`：基于已有 universe 数据集只补拉缺失日期
  - 支持 `--write-latest-alias`：额外输出稳定文件 `*_latest_*.csv`
  - 支持 `--bootstrap-start`：增量模式下对缺失 symbol 的历史回填起点
- [fetch_stock_metadata.py](C:/Users/Apricity/Desktop/股票/data_module/fetchers/scripts/fetch_stock_metadata.py)
  拉取行业等元数据
- [normalize_ohlcv.py](C:/Users/Apricity/Desktop/股票/data_module/fetchers/scripts/normalize_ohlcv.py)
  对已有 CSV 做 schema 归一化

## 当前支持的数据源

### demo

- 用随机生成的业务日样本模拟价格与成交量
- 不依赖第三方财经接口
- 主要用于测试整条链路是否对齐

### akshare

- 当前 A 股主数据源
- 日线抓取优先使用 `stock_zh_a_hist`
- 若 Eastmoney 不稳定，会 fallback 到新浪日线接口
- 行业元数据也通过 AkShare 的 CNINFO 接口获取

### stooq

- 当前美股 zero-shot 测试数据源
- 通过 Stooq 日线 CSV 接口获取数据
- 已用于 30 只美股大盘股的真实实验

## 输出产物

单股抓取默认输出：

- `raw.csv`
- `normalized.csv`
- `manifest.json`

股票池抓取默认输出：

- 每支股票各自的 `raw/normalized/manifest`
- 合并后的 universe `normalized.csv`
- universe 级别 `manifest.json`
- 可选稳定别名 `*_latest_*.csv` 与 `*_latest_*.json`

## 元数据抓取

当前元数据模块支持两条线：

- A 股：CNINFO 行业变更历史
- 美股：Wikipedia S&P 500 表格中的 GICS 行业分类

## 当前已验证流程

### A 股

1. 用 `fetch_stock_universe.py` 拉取股票池
2. 输出到 `data/interim/akshare/universes/`
3. 直接交给 `model_prediction/lightgbm`

### 美股

1. 用 `fetch_stock_universe.py --provider stooq`
2. 用 `fetch_stock_metadata.py --provider wikipedia_sp500`
3. 产物直接进入 zero-shot 推理和风控回测

### 美股（Alpaca 生产）

1. 首次全量：`fetch_stock_universe.py --provider alpaca --start 1990-01-01 ... --write-latest-alias`
2. 夜间增量：`fetch_stock_universe.py --provider alpaca --incremental --write-latest-alias`
3. 下游统一消费 `data/interim/alpaca/universes/us_large_cap_30_latest_hfq_normalized.csv`

## 重要约束

- `fetchers` 的目标是统一输出，不是长期承载复杂清洗逻辑
- 如果未来出现大量缺失值处理、复权处理或多表对齐逻辑，建议迁移到 `cleaning` 模块

## 当前注意点

- 美股 Stooq 数据已经可用，但当前部分输出文件名仍沿用了旧的 `_hfq_` 命名惯例
- 这是命名遗留，不影响本次实验数据内容

## 后续建议

- 增加更稳定的美股数据源备用通道
- 为股票池抓取增加市场模板配置
- 把 provider 的字段差异尽可能在抓取层消化掉
