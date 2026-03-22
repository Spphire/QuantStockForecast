# 模块说明：execution

## 职责

`execution` 负责把目标仓位转成下单意图，并在 paper 运行时内完成提交、状态追踪、对账与运维。

## 分层

- `execution/common/`
  - 执行模型、计划校验、对账、状态写盘
- `execution/alpaca/`
  - Alpaca broker 适配与下单路由
- `execution/managed/`
  - 产品化运行时应用（`paper_daily`, `paper_ops`, `paper_smoke`）
- `execution/strategies/`
  - 策略配置（输入源、账户前缀、执行参数）

## 关键入口命令

运行策略（dry-run）：

```powershell
python -m execution.managed.apps.run_multi_expert_paper execution/strategies/us_zeroshot_a_share_multi_expert_daily.json
```

日常统一入口：

```powershell
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json run
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json healthcheck
```

运维查看：

```powershell
python -m execution.managed.apps.paper_ops execution/strategies/us_zeroshot_a_share_multi_expert_daily.json latest-run
```

## 关键配置项（strategy JSON）

- `strategy_id`：策略唯一 ID
- `paper_env_prefix`：Alpaca 凭据前缀
- `source.path`：`risk_positions.csv` 路径
- `source.summary_path`：`risk_summary.json` 路径
- `execution.*`：下单模式、仓位上限、最小订单金额、重试等参数

## 主要落盘目录

- 运行时文件：`execution/runtime/<strategy_id>/<timestamp>/`
- 最新快照：`execution/runtime/<strategy_id>/latest/`
- 状态与日志：`execution/state/<strategy_id>/`
- 账本：`artifacts/paper_trading/<strategy_id>/paper_ledger.sqlite3`

