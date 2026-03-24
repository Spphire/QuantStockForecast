# 21 Owner 任务矩阵（Day1-Day10）

更新时间：`2026-03-24`（`Asia/Shanghai`）

## 1. SA-Data

1. `SD1`（CP）：冻结分钟行情批次契约与必填字段。
2. `SD2`（CP）：实现数据新鲜度/覆盖率/重复 bar 校验。
3. `SD3`（CP）：实现市场时钟与开市状态采集。
4. `SD4`（CP）：产出 `feature_cutoff_ts` 与 `next_bar_open_ts`。
5. `SD5`：构建脏数据与时钟异常测试夹具。
6. `SD6`：接入 pre-open 30 分钟数据预检。
7. `SD7`：输出数据稳定性基线报告。

## 2. SA-RiskExec

1. `SE1`（CP）：落分钟账本与唯一键。
2. `SE2`（CP）：实现 `run_lock` 与 slot 级幂等守卫。
3. `SE3`（CP）：打通 `decision-engine -> execution-watchdog` 单写链。
4. `SE4`（CP）：动作投影与 white-box 桥接。
5. `SE5`（CP）：动作生效率监控接入。
6. `SE6`（CP）：runtime/simulator 共用 fill contract。
7. `SE7`：stale order cleanup 与账户保护模式。
8. `SE8`：执行链路集成演练。

## 3. SA-RL

1. `SR1`（CP）：冻结 reward 归因模型与表结构。
2. `SR2`（CP）：实现 `5min/30min` 回填与 replay 分桶。
3. `SR3`（CP）：落训练只读 ledger 边界。
4. `SR4`（CP）：训练健康门禁。
5. `SR5`（CP）：OOD 门禁实现与配置冻结。
6. `SR6`：样本无效化与污染回收。
7. `SR7`：RL 数据面 smoke 与漂移演练。

## 4. SA-Ops

1. `SO1`（CP）：因果审计 hard gate。
2. `SO2`（CP）：上线前检查单串联脚本。
3. `SO3`（CP）：simulator 校准与 scope 注册。
4. `SO4`（CP）：晋级裁决脚本。
5. `SO5`：paper/live 证据 lint。
6. `SO6`（CP）：降级恢复状态机与 drill。
7. `SO7`：runbook 动作脚本化（对账与污染扫描）。
8. `SO8`（CP）：发布演练与 go/no-go 签字包。
9. `SO9`（CP）：`stable_bundle_manifest` 整包回滚机制与回滚演练。

## 5. 关键路径链路

1. `CP1`: `SD1 -> SE1 -> SE2 -> SE3`
2. `CP2`: `SD2 + SD3 + SD4 -> SO1 -> SO2`
3. `CP3`: `SE3 -> SE4 -> SE5 -> SR1 -> SR2 -> SR3 -> SR4 -> SR5 -> SO6`
4. `CP4`: `SE6 -> SO3 -> SO4`
5. `CP5`: `SO2 + SO4 + SO5 + SO6 + SO8 + SO9`（最终上线阻断链）
