# Data Module

`data_module` 负责项目里的数据输入层。它的目标不是只“抓到数据”，而是把不同来源的数据整理成 **统一、可建模、可复用** 的格式。

## 当前职责

- 管理统一股票数据 schema
- 拉取单支股票或股票池数据
- 拉取行业等元数据
- 为下游特征工程和模型训练提供稳定输入

## 当前结构

- [common/README.md](C:/Users/Apricity/Desktop/股票/data_module/common/README.md)
  共享 schema 与标准化函数
- [fetchers/README.md](C:/Users/Apricity/Desktop/股票/data_module/fetchers/README.md)
  已实现的数据抓取模块
- [cleaning/README.md](C:/Users/Apricity/Desktop/股票/data_module/cleaning/README.md)
  预留的数据清洗模块
- [crawlers/README.md](C:/Users/Apricity/Desktop/股票/data_module/crawlers/README.md)
  预留的网页爬虫模块
- [features/README.md](C:/Users/Apricity/Desktop/股票/data_module/features/README.md)
  预留的特征层模块

## 当前已实现能力

- 单支股票历史行情抓取
- 股票池合并抓取
- 行业元数据抓取
- 多源字段归一化
- 原始层、标准化层、manifest 输出

## 已验证的数据源

- `demo`
  用于无依赖 smoke test
- `akshare`
  用于 A 股历史行情和行业元数据
- `stooq`
  用于美股 zero-shot 测试

## 统一输入输出约束

当前所有可建模数据都应该最终变成：

- `date`
- `symbol`
- `open`
- `high`
- `low`
- `close`
- `volume`

可选增强字段包括：

- `amount`
- `turnover`
- `pct_change`
- `price_change`
- `amplitude`
- `provider`
- `adjust`

## 输出目录约定

- 原始数据：`data/raw/...`
- 标准化数据：`data/interim/...`
- 处理后数据：`data/processed/...`

## 当前状态

- `fetchers` 已可用于真实实验
- `common` 已形成稳定契约
- `cleaning / crawlers / features` 目前还是规划模块，尚未独立成型

## 推荐使用方式

当前推荐先通过 `fetchers` 拿到稳定的标准化 CSV，再交给 `model_prediction` 侧做特征工程与训练。后续如果数据流程变复杂，再逐步把清洗和特征生产从训练脚本中剥离到独立模块。
