# Execution

`execution` 负责把风控层给出的目标仓位转成可执行订单，并维护 paper 运行时状态。

## 关键分层

- `execution/common/`：执行模型、计划构建、对账、状态写盘
- `execution/alpaca/`：Alpaca Broker 适配
- `execution/managed/`：产品化运行时应用（paper_daily / paper_ops / paper_smoke）
- `execution/strategies/`：策略配置

## 常用入口

```powershell
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json healthcheck
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json run
python -m execution.managed.apps.paper_ops execution/strategies/us_zeroshot_a_share_multi_expert_daily.json latest-run
```

## 运行时落盘

- `execution/runtime/<strategy_id>/<timestamp>/`
- `execution/runtime/<strategy_id>/latest/`
- `execution/state/<strategy_id>/`
- `artifacts/paper_trading/<strategy_id>/paper_ledger.sqlite3`

## 进一步阅读

- `docs/modules/execution.md`
- `docs/workflows/paper-trading-daily.md`
- `docs/operations/windows-scheduler.md`

