# Windows Scheduler Guide

## Goal

把当前仓库接成“外部调度器驱动”的日常系统，而不是依赖人工定闹钟。

推荐拆成两类任务：

1. 收盘后研究任务
2. 开盘后提交任务

## Why This Shape

当前仓库的执行入口是单次运行型：

- `python -m execution.managed.apps.paper_daily ... run`
- `python -m execution.managed.apps.run_multi_expert_paper ...`

它们不是常驻进程，所以最适合交给 Windows Task Scheduler 定时拉起。

## Wrapper Scripts

已经提供两个给任务计划程序调用的脚本：

- [invoke_daily_research_pipeline.ps1](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/windows/invoke_daily_research_pipeline.ps1)
- [invoke_market_open_submit.ps1](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/windows/invoke_market_open_submit.ps1)

辅助函数：

- [_common.ps1](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/windows/_common.ps1)

## Recommended Schedule

### Task 1: Nightly Research

作用：

- 更新 U.S. universe 数据
- 跑两套 expert prediction + ensemble
- 生成两套 `risk_positions.csv` / `risk_actions.csv`

建议在 Windows 里配两个触发器：

- `Tue-Sat 05:30` Asia/Shanghai
- `Tue-Sat 06:30` Asia/Shanghai

原因：

- 美股夏令时和冬令时会让中国时间相差 1 小时
- 这个脚本自带纽约时间窗口检查，只会在 `16:10-20:00 America/New_York` 执行
- 所以双触发器是为了自动跨越 DST，不需要你每年改计划

Action:

```text
powershell.exe
```

Arguments:

```text
-ExecutionPolicy Bypass -File "C:\Users\Apricity\Desktop\QuantStockForecast\execution\scripts\windows\invoke_daily_research_pipeline.ps1"
```

Start in:

```text
C:\Users\Apricity\Desktop\QuantStockForecast
```

### Task 2: Market Open Submit

作用：

- 先做 healthcheck
- 再按两条策略分别执行 `paper_daily run --submit --require-paper`
- 最后打印 `paper_ops latest-run`

建议在 Windows 里配两个触发器：

- `Mon-Fri 21:35` Asia/Shanghai
- `Mon-Fri 22:35` Asia/Shanghai

原因：

- 对应美股开盘后几分钟
- 同样通过“双触发器 + 纽约时间窗口检查”解决 DST 切换问题
- 脚本还会再查 Alpaca broker clock，确认 `is_open=true` 才真的提单

Action:

```text
powershell.exe
```

Arguments:

```text
-ExecutionPolicy Bypass -File "C:\Users\Apricity\Desktop\QuantStockForecast\execution\scripts\windows\invoke_market_open_submit.ps1"
```

Start in:

```text
C:\Users\Apricity\Desktop\QuantStockForecast
```

## Safety Notes

- 默认不要传 `--skip-session-guard`
- 默认不要传 `--allow-unhealthy`
- 当前策略配置里已经有 `cancel_open_orders_first=true`
- 如果同一交易日重复触发，`session_guard` 会阻止重复提单
- `invoke_market_open_submit.ps1` 还会检查 broker clock 是否 open

## Manual Dry Runs

如果你想先手动验证 wrapper，可这样跑：

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\invoke_daily_research_pipeline.ps1 -IgnoreTimeWindow
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\invoke_market_open_submit.ps1 -IgnoreTimeWindow
```

说明：

- `-IgnoreTimeWindow` 只忽略脚本自己的纽约时间窗判断
- `invoke_market_open_submit.ps1` 仍然会检查 Alpaca broker clock

## Operational Reality

这套调度方案适合当前阶段的 `paper` 运维，但它依然是“定时批处理系统”，不是完整无人值守交易平台。

当前仍建议你每天至少看一次：

- `execution/state/<strategy>/latest_state.json`
- `paper_daily healthcheck`
- `paper_ops latest-run`
- Alpaca paper 账户里的 open orders / filled orders
