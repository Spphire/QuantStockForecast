# Windows Scheduler Guide

## Goal

把当前仓库接成“外部调度器驱动”的日常系统，而不是依赖人工定闹钟。

推荐拆成两类任务：

1. 收盘后研究任务
2. 开盘后提交任务

## Wrapper Scripts

Windows 任务计划程序直接调用这三份脚本：

- [invoke_daily_research_pipeline.ps1](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/windows/invoke_daily_research_pipeline.ps1)
- [invoke_market_open_submit.ps1](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/windows/invoke_market_open_submit.ps1)
- [register_scheduler_tasks.ps1](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/windows/register_scheduler_tasks.ps1)

辅助函数：

- [_common.ps1](C:/Users/Apricity/Desktop/QuantStockForecast/execution/scripts/windows/_common.ps1)

## Recommended Schedule

### Nightly Research

作用：

- 更新 U.S. universe 数据
- 跑两套 expert prediction + ensemble
- 生成两套 `risk_positions.csv` / `risk_actions.csv`

建议在上海时间配两个触发器：

- `Tue-Sat 05:30`
- `Tue-Sat 06:30`

原因：

- 中国时间会因为美股 DST 切换前后相差 1 小时
- 这个脚本自带纽约时间窗口检查，只会在 `16:10-20:00 America/New_York` 执行
- 双触发器只是为了跨越 DST，不会真的重复跑两次有效任务

### Market Open Submit

作用：

- 先做 healthcheck
- 再按两条策略执行 `paper_daily run --submit --require-paper`
- 最后落盘 operator brief 并可选发送飞书消息

建议在上海时间配两个触发器：

- `Mon-Fri 21:35`
- `Mon-Fri 22:35`

原因：

- 对应美股开盘后几分钟
- 同样通过“双触发器 + 纽约时间窗口检查”解决 DST 切换问题
- 脚本还会再查 Alpaca broker clock，确认 `is_open=true` 才真的提单

## One-Click Registration

如果你不想手动点 Windows UI，可以直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\register_scheduler_tasks.ps1
```

它会注册 2 个任务：

- `QuantStockForecast Nightly Research`
- `QuantStockForecast Market Open Submit`

## Brief Outputs

两个 wrapper 每次运行后都会自动生成图文化简报。默认最新路径：

- `artifacts/ops_briefs/research/latest/brief.html`
- `artifacts/ops_briefs/research/latest/dashboard.png`
- `artifacts/ops_briefs/research/latest/brief.md`
- `artifacts/ops_briefs/submit/latest/brief.html`
- `artifacts/ops_briefs/submit/latest/dashboard.png`
- `artifacts/ops_briefs/submit/latest/brief.md`

简报内容默认包含：

- 目标仓位饼图
- 动作或订单状态柱状图
- 账户资金摘要
- 健康检查告警
- 面向新手的一句话解释
- 下一步建议动作

推荐查看方式：

- 先打开 `brief.html`
- 再看 `dashboard.png`
- 需要在终端或 Git 记录里留痕时看 `brief.md`

## Feishu Notification

如果你想让每次任务结束后自动推送一条飞书消息，可给当前 Windows 用户设置：

```powershell
setx QSF_FEISHU_WEBHOOK_URL "https://open.feishu.cn/open-apis/bot/v2/hook/..."
```

脚本会自动把简报摘要、本地 HTML 路径和 PNG 路径推送到飞书群机器人。没有配置这个变量时，任务仍会正常运行，只是不发送外部通知。

如果你更希望把 webhook 和签名密钥持久化到本地 config，也可以把：

- [ops_notifications.example.json](C:/Users/Apricity/Desktop/QuantStockForecast/configs/ops_notifications.example.json)

复制为本地文件 `configs/ops_notifications.local.json` 后再填入 `webhook_url` 和 `secret`。

当前优先级是：

1. `configs/ops_notifications.local.json`
2. `QSF_FEISHU_WEBHOOK_URL` / `QSF_FEISHU_WEBHOOK_SECRET`

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
