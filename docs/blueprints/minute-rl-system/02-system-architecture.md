# 02 系统架构与复用映射

## 1. 总体架构

1. 采用旁路子系统，不侵入当前日频主链路。
2. 分钟系统与日频系统共享“信号-风控-执行”契约，但目录与运行态完全隔离。
3. 分钟系统所有关键状态统一落在 ledger/event store，作为唯一真相源。

## 2. 推荐目录

```text
docs/blueprints/minute-rl-system/
minute_system/
  configs/
  data/
  experts/
  ensemble/
  rl/
  risk/
  execution/
  ops/
```

## 3. 复用点（当前仓库）

| 模块 | 复用内容 | 新增内容 |
|---|---|---|
| `data_module/fetchers` | Alpaca 拉取与增量框架 | 分钟级抓取与分片落盘 |
| `model_prediction/common` | expert 调度、信号标准化 | 分钟级特征/模型适配 |
| `risk_management/white_box` | 风控规则与仓位输出契约 | 分钟模式参数模板 |
| `execution/managed` | 提交、对账、账本、监控 | 分钟循环编排、watchdog、run lock |
| `execution/managed/monitoring` | 简报与告警通道 | 分钟级健康指标与告警模板 |

## 4. 进程拓扑（强约束）

1. `data-ingest`：拉分钟行情并写数据层。
2. `decision-engine`：构建 state、推理动作、调用 white-box 生成目标仓位。
3. `execution-watchdog`：唯一允许写订单/成交/持仓状态回 ledger 的进程。
4. `training-worker`：仅从 ledger/event store 读取训练样本，不直接读 broker API。

## 5. 并存与回滚

1. 分钟策略统一前缀：`us_minute_*`。
2. 分钟运行目录独立：`execution/runtime/us_minute_*`、`execution/state/us_minute_*`。
3. 分钟开关：
   - `QSF_ENABLE_MINUTE_RUNTIME`
   - `QSF_MINUTE_DRY_RUN_ONLY`
   - `QSF_MINUTE_KILL_SWITCH_PATH`
4. 回滚步骤：
   - 停分钟调度。
   - 打开 minute kill switch。
   - 保留日频任务继续运行。
