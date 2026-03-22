# 工作流：日常 Paper Trading

## 目标

在开盘时段按策略提交订单，并保留可审计运行记录。

## 推荐流程

1. 先健康检查
2. 再执行 run（dry-run 或 submit）
3. 最后用 `paper_ops` 回看状态

## 命令清单

健康检查：

```powershell
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json healthcheck
```

Dry-run：

```powershell
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json run
```

提交到 paper：

```powershell
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json run --submit --require-paper
```

查看最近一次：

```powershell
python -m execution.managed.apps.paper_ops execution/strategies/us_zeroshot_a_share_multi_expert_daily.json latest-run
```

## 调度包装入口

开盘提交包装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\invoke_market_open_submit.ps1
```

调试时可跳过时间窗判断：

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\invoke_market_open_submit.ps1 -IgnoreTimeWindow
```

## 风险开关

- Kill switch 文件默认位置：`artifacts/paper_trading/<strategy>/paper_daily.kill`
- 非必要不要使用：
  - `--allow-unhealthy`
  - `--skip-session-guard`

