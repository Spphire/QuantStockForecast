# QuantStockForecast 文档中心

这套文档只保留当前仍在运行的主线能力，重点覆盖以下内容：

- 系统架构与模块边界
- 从数据到执行的端到端工作流
- 日常运维与调度
- 测试与回归检查

## 从这里开始

- [快速开始](quickstart.md)
- [架构总览](architecture/overview.md)

## 按模块阅读

- [数据模块](modules/data_module.md)
- [预测模块](modules/model_prediction.md)
- [风控模块](modules/risk_management.md)
- [执行模块](modules/execution.md)

## 按流程阅读

- [夜间研究流水线](workflows/research-pipeline.md)
- [日常 Paper Trading 流程](workflows/paper-trading-daily.md)
- [Ablation 实验计划（Alpaca）](workflows/alpaca-ablation-plan.md)
- [实战优化 TODO 看板](workflows/ops-optimization-todo.md)

## 前瞻蓝图

- [分钟级 RL 量化交易子系统蓝图（多文件）](blueprints/minute-rl-system/README.md)

## 运维与质量

- [Windows 调度指南](operations/windows-scheduler.md)
- [测试与回归](quality/testing.md)

## 历史说明

历史实验文档不再保留在仓库工作目录中，统一以 Git 历史版本追溯。  
当前 `docs/` 目录仅维护主线运行文档。
