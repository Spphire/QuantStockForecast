# 运维：Windows 调度

## 推荐任务

当前仓库默认注册 4 个任务（为 DST 提供双时段兜底）：

- `QuantStockForecast-NightlyResearch-0530`
- `QuantStockForecast-NightlyResearch-0630`
- `QuantStockForecast-MarketOpenSubmit-2135`
- `QuantStockForecast-MarketOpenSubmit-2235`

对应脚本：

- `execution/scripts/windows/invoke_daily_research_pipeline.ps1`
- `execution/scripts/windows/invoke_market_open_submit.ps1`

## 一键注册

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\register_scheduler_tasks.ps1
```

仅预览命令不创建：

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\register_scheduler_tasks.ps1 -WhatIf
```

## 时间窗约束

- 研究任务仅在纽约时间 `16:10-20:00` 执行
- 提交任务仅在纽约时间 `09:31-10:00` 执行
- 即使任务被触发，脚本也会因时间窗不满足而安全退出

## 建议巡检

每天至少检查：

- `execution/state/<strategy>/latest_state.json`
- `python -m execution.managed.apps.paper_daily <strategy_config> healthcheck`
- `python -m execution.managed.apps.paper_ops <strategy_config> latest-run`

