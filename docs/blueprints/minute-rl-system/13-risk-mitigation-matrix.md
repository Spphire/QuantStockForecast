# 13 风险与缓解矩阵

## 1. 风险评分矩阵（红队）

评分：概率/影响/可检测性（1-5，越高越大）

| 风险 | 概率 | 影响 | 可检测性 | 当前控制 | 剩余风险 |
|---|---:|---:|---:|---|---|
| 时间因果泄露/错位 | 3 | 5 | 4 | 时序契约 + 1000条抽检0违规 | 边角路径绕开契约 |
| reward 归因错误 | 3 | 5 | 3 | 即时/延迟拆分 + 主口径固定 | 多订单回填错配 |
| white-box 裁剪过强 | 4 | 4 | 4 | gap/binding/clip 门槛 | 样本效率损失 |
| IQL->SAC OOD 漂移 | 3 | 5 | 2 | 动作边界 + OOD监控 + 基线降级 | 早期轻微漂移难识别 |
| 模拟器偏差 | 4 | 5 | 3 | 校准阈值 + fail-close | 市场状态切换失真 |
| 极端波动跳空 | 3 | 5 | 4 | 极端场景降级 runbook | 新型极端态覆盖不足 |
| 流动性骤降 | 4 | 4 | 3 | fill/slippage/stale 监控 | 慢性恶化识别延迟 |
| 批量 reject / broker 异常 | 3 | 5 | 5 | reject 门槛 + kill switch | 间歇性复发 |
| 账本污染/幂等失效 | 2 | 5 | 4 | 唯一键 + 单写路径 + run lock | 一旦发生污染面大 |
| 配置漂移/人为误操作 | 3 | 4 | 4 | 版本字段 + 白名单 + runbook | 临时改参风险 |

## 2. 工程缓解矩阵（蓝队）

| 风险 | Owner | 落地文件 | 截止里程碑 | 验收标准 |
|---|---|---|---|---|
| 因果契约 | SA-Data + SA-RiskExec | `appendix/A...`, `05...` | M0 | 时序规则写死 + 1000条0违规 |
| OOD 漂移 | SA-RL | `03...`, `06...` | M1 | challenger-only + OOD门槛 |
| reward 错配 | SA-RL + SA-RiskExec | `04...`, `appendix/A...` | M0 | action_id/reward_id 可追溯 |
| 动作耦合 | SA-RL | `03...` | M0 | 分阶段解耦落文档 |
| 状态过粗 | SA-Data + SA-RiskExec | `02...`, `03...` | M1 | 执行态特征补齐 |
| 白盒屏蔽 | SA-RiskExec + SA-RL | `05...`, `03...` | M1 | gap/binding 触发摘维 |
| A/B 证据力 | SA-Ops + SA-RiskExec | `06...` | M2 | 同时刻同时钟三层对照 |
| 晋级门槛 | SA-Ops + SA-RL | `06...`, `appendix/B...` | M0 | shadow>=10, bootstrap>=0.65, reject/slippage门槛 |
| replay 偏见 | SA-RL | `04...`, `07...` | M2 | regime-aware replay 分桶 |
| ablation 不足 | SA-RL + SA-Ops | `04...`, `06...` | M2 | 最小ablation全覆盖 |
