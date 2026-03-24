# 22 研究验收矩阵（Research Acceptance Matrix）

更新时间：`2026-03-24`（`Asia/Shanghai`）

| Now项 | 通过证据 | 拒绝证据 | 最低样本量 | 主要误判来源 | 防误判动作 |
| --- | --- | --- | --- | --- | --- |
| 分钟账本字段完整 | 因果时戳与核心ID非空率100%，链路可回放 | 缺字段、断链、事后补写 | `>=1000` transition, `>=300` terminal order | 字段存在但值无效 | `write_once` + `source_process_id` 审计 |
| 单写边界 | 仅 watchdog 写执行状态；trainer 无 broker 读取 | 非watchdog写入、trainer旁路broker | `>=5`有效日审计全通过 | 临时脚本绕边界 | DB ACL + CI 依赖扫描 |
| 幂等与run lock | 同唯一键不重复提交 | 同键多终态、重复下单 | `>=1000` slot + `>=50`重放注入 | 把网络重试当同单 | 提交前硬查唯一键 + 唯一约束 |
| 因果审计门 | `sample>=1000` 且 `violation=0`，含 `norm_asof` 检查 | 样本不足、任一违规 | 每次评审 `>=1000` | 只抽干净时段 | 分层抽样覆盖 pre-open/open/close/stress |
| reward归因 | `coverage>=99.5%` 且 unresolved notional `<=0.1%` equity | 多对一或一对多错挂、冲突未标记 | `>=100` action 回放, `>=500` reward leg | 聚合对但分项错挂 | 以 `reward_leg_id` 做最小核对单元 |
| replay分桶 | 主桶无 invalid，invalid 正确传播到 30min 窗口 | 当前slot作废但延迟reward仍入主桶 | `>=30`传播测试 + 主桶抽检 `>=1000` | 忽略窗口传播 | `propagated_reward_window_end_ts` 强制检查 |
| fill rule 冻结 | 单一 `fill_rule_version`，无 `first_fill < next_bar_open` | 同窗口多rule或same-bar fill | `>=5`有效paper日, `>=300` terminal order | 把价格代理当时点代理 | 时点规则与价格代理字段拆分 |
| OOD门禁 | 双指标（`state_md_score + bc_action_nll`）+ 冻结参考桶 + 可触发freeze | 单指标、在线重估阈值、连续窗口未定义 | 每scope `>=5000` transition + 注入 `>=20` case | 只看状态或只看行为 | 20-slot 连续窗口（3次warning/5次freeze/2日恢复）写死在配置 |
| scope_hash 一致性 | 校准/OOD/晋级三处 `scope_hash` 完全一致 | 任一环节 `scope_hash` 漂移或缺失 | 每次评审前全量一致性检查 | 错域样本混用 | 统一 `scope_hash_builder` + CI 一致性校验 |
| 校准与晋级 | TTL/scope有效，paired effective-day bootstrap可复现 | 过期/错域/非paired评审 | 校准 `>=5`日 `>=300`单；晋级 `>=10+10`有效日 | 拼窗口导致偏差 | 评审前先跑 TTL/scope gate |
| 恢复状态机 | 触发后执行 `DEGRADED->COOLDOWN->SHADOW_ONLY`；`cooldown=30min`；同日二次触发锁至收盘；恢复需 `10` slot shadow + `30` clean slot | 跳步恢复、同日二次触发自动恢复、缺冷却期 | `>=20` 次状态机 drill（含二次触发场景） | 恢复振荡被误当策略能力 | 固定状态机与 drill 脚本，人工 override 必须落盘审批 |
| 样本与结论边界 | paper报告带 `evidence_scope` 与 disclaimer | 缺scope或误表述为 live-ready | 所有评审报告全量检查 | 文案越界 | `report_linter` 自动失败拦截 |
