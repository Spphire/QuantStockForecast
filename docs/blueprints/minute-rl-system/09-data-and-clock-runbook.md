# 09 数据异常与时钟漂移 Runbook

## 场景 B1：行情断档 / 数据不新鲜

### 触发

1. `bar_lag_seconds > 90` 连续 3 个 slot。
2. `bar_lag_seconds > 300` 任意一次。
3. 股票池 bar 覆盖率 `< 95%`。

### 自动处置

1. 当前 slot `skip-trading`。
2. challenger 切 `shadow-only`。
3. 停止该 slot 的在线训练与 reward 结算写入。
4. 连续 5 个 slot 触发则降级到基线或 `dry-run only`。

### 恢复

1. 连续 10 个 slot `bar_lag_seconds <= 90`。
2. 覆盖率 `>= 99%`。
3. 恢复后先 shadow，不直接恢复晋级流程。

## 场景 B2：脏数据 / 重复 bar / schema 漂移

### 触发

1. 非法值：`close <= 0`、`high < low`、`volume < 0`、`amount < 0`。
2. 同 `symbol + bar_close_ts` 出现重复且数值冲突。
3. 必需字段缺失或类型漂移。

### 自动处置

1. 阻断当前 slot 信号与下单。
2. 标记当前批次 `invalid_market_batch`。
3. 禁止该批次进入 white-box / replay / 训练。
4. schema 漂移触发时全局切 `dry-run only`。

### 恢复

1. schema 校验恢复通过。
2. 重复冲突 bar 清理并重落盘。
3. 连续 5 个 slot 无新增数据完整性告警。
4. 恢复后首交易日只允许 shadow。

## 场景 B3：时钟漂移 / 事件顺序反转

### 触发

1. 本地时钟与基准时间偏差 `> 500ms`。
2. 进程间偏差 `> 1000ms`。
3. 事件顺序异常：`submit_ts < decision_ts` 或 `first_fill_ts < submit_ts`。

### 自动处置

1. 暂停新决策、新下单、在线训练。
2. 切 `safe-hold`，仅允许 watchdog 管理既有 open orders。
3. 漂移 `> 2000ms` 时直接 `dry-run only`。

### 恢复

1. 核心进程与基准偏差 `<= 200ms`。
2. 连续 30 个 slot 无事件顺序反转。
3. 恢复后先运行 10 个 slot shadow-only，再逐步放开。
