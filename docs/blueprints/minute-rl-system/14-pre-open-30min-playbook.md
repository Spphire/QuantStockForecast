# 14 开盘前 30 分钟压力场景与响应

更新时间：`2026-03-23`（`Asia/Shanghai`）

## 1. 红队压力场景（最易击穿）

| 场景 | 触发条件 | 覆盖状态 | 最小新增条款 | 通过标准 |
| --- | --- | --- | --- | --- |
| 交易日历/开市状态误判 | `market_clock` 未开市但调度开始下单，或 `next_bar_open_ts` 与 broker `is_open` 冲突 | 部分 | `broker is_open=false` 或日历未确认开市时，前 30 分钟禁止新开仓，仅 dry-run。 | 前 30 分钟内若 `is_open=false`，`submitted_orders=0` |
| 跳空后熔断/停牌 | 跳空 `>=3%` 且出现 `halted/LULD` 或连续无成交 bar | 部分 | 出现 `halt/LULD` 的 symbol 当日移出 universe，且样本不入主 replay。 | 触发后该 symbol `new_submissions=0`，主 replay 无新增样本 |
| 数据面不完整仍决策 | 股票池 bar 覆盖率 `<95%` 或核心标的连续缺失 `>=2` bar | 是 | 无 | 触发后 `decision_count=0` 或切 `dry-run only` |
| 卖单未终态就提交买单 | `open sell orders > 0` 同时继续提交依赖资金释放的新买单 | 部分 | 若存在未终态卖单，禁止提交依赖其资金的新买单。 | `dependent_buy_submissions=0`，现金不足 reject 不上升 |
| cancel/replace 链路卡死 | `cancel_ack_timeout` 超阈值且 `open_order_age_p95 > 300s` | 部分 | 触发后立即停止新开仓并切基线/只减仓模式。 | `new_open_orders=0`，`open_order_age_p95` 回落 |

## 2. 蓝队快速响应 Playbook

### 2.1 Broker 时钟异常

- `trigger`: broker 状态与本地预开盘判断不一致。
- `immediate auto action`: 暂停 submit，锁定新订单入口，切 `pre-open hold`。
- `operator checklist`:
  - 核对 broker clock、交易日历、账户权限。
  - 确认是否半日市/节假日/临停。
  - 重新拉取 market clock 与 account snapshot。
- `rollback condition`: 连续两次校验不一致或距开盘不足 10 分钟仍未恢复，取消当次开盘执行，仅保留 shadow。

### 2.2 账户与目标仓位不一致

- `trigger`: 盘前持仓快照与系统预期仓位差异明显。
- `immediate auto action`: 停止正式下单，进入 `reconcile-only`。
- `operator checklist`:
  - 检查残留订单或人工操作。
  - 核对 broker positions 与 ledger state。
  - 决定是否先跑只读 reconciliation。
- `rollback condition`: 关键差异无法在开盘前解释，禁用 challenger，仅 baseline 或 dry-run。

### 2.3 盘前流动性骤降

- `trigger`: 点差异常放大、可成交量异常低、预估滑点抬升。
- `immediate auto action`: 收缩 gross exposure，降低执行强度，取消新增开仓。
- `operator checklist`:
  - 判断异常是局部 symbol 还是全市场。
  - 核对是否有新闻/财报/复牌事件。
  - 评估是否临时剔除异常 symbol。
- `rollback condition`: 若核心标的执行成本持续超阈值至开盘前 5 分钟，取消主动建仓，仅允许减仓/观望。

### 2.4 残留未完成订单占用 buying power

- `trigger`: 开盘前仍有大量 `new/open/partially_filled` 订单。
- `immediate auto action`: watchdog 进入 `cleanup-first`，暂停新买单，先清旧单再决策新单。
- `operator checklist`:
  - 确认残留单来源。
  - 判断保留单与可撤单。
  - cleanup 后复核 buying power。
- `rollback condition`: 残留单未收敛到安全水平，禁止新开仓，仅允许清理与被动风险控制。

### 2.5 简报/监控通道失效

- `trigger`: Feishu 或监控推送失败，但交易链路正常。
- `immediate auto action`: 不立即停交易，自动落盘 incident 与 pre-open snapshot，切 `notify-degraded`。
- `operator checklist`:
  - 检查 webhook/network 或渲染故障。
  - 确认 run manifest、account snapshot、execution preview 已落盘。
  - 决定是否人工复核后继续 baseline。
- `rollback condition`: 监控失效叠加任一执行风险信号，直接取消当次开盘执行。
