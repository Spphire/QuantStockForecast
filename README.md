# QuantStockForecast

面向股票研究与 Paper Trading 的模块化量化项目，主线链路为：

`数据抓取与标准化 -> 多 expert 预测 -> 白盒风控 -> 执行运行时`

## 模块分层

- `data_module/`
  - 数据抓取、元数据抓取、统一 schema 标准化
- `model_prediction/`
  - lightgbm/xgboost/catboost/lstm/transformer/ensemble
- `risk_management/white_box/`
  - 信号过滤、选股、仓位、换手、回测统计
- `execution/`
  - Alpaca 适配、策略运行、账本、运维工具

## 快速入口

安装：

```powershell
python -m pip install -e .
python -m pip install -e .[dev]
```

研究流水线（生成 `risk_positions.csv`）：

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\invoke_daily_research_pipeline.ps1 -IgnoreTimeWindow
```

Paper 运行（健康检查 + dry-run / submit）：

```powershell
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json healthcheck
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json run
```

## 文档导航

- [文档首页](docs/README.md)
- [快速开始](docs/quickstart.md)
- [架构总览](docs/architecture/overview.md)
- [模块说明](docs/modules/data_module.md)
- [研究流水线](docs/workflows/research-pipeline.md)
- [Paper Daily 流程](docs/workflows/paper-trading-daily.md)
- [Windows 调度](docs/operations/windows-scheduler.md)
- [测试与回归](docs/quality/testing.md)

## 历史资料

旧版 docs 已完整备份到 `docs_backup_2026-03-22/`，用于追溯历史实验与开发日志。
