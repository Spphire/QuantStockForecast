# 附录 C 主线程监督日志（2026-03-23）

时区：`Asia/Shanghai`

## 阶段一（至 24:00）两专家攻防迭代

### Round 1（约 23:11-23:14）

1. 红队输出 Top5 阻断：因果契约、IQL->SAC 漂移、reward 归因、动作生效率、晋级证据力。
2. 蓝队输出 Top5 返工点及最小补丁条款。
3. 主线程动作：进入阈值量化收敛轮。

### Round 2（约 23:14-23:16）

1. 红队给出“可接受最低阈值区间”及“不可谈判项”。
2. 蓝队提交 Final Threshold Table（数字化阈值）。
3. 主线程动作：将阈值回写到
   - `05-runtime-safety-and-ops.md`
   - `06-simulator-ab-and-promotion.md`

### Round 3（约 23:16-23:18）

1. 红队终审初判：`有条件通过`，剩余两条阻断：
   - 因果契约缺 `eligible_fill_start_ts` 与主奖励窗口写死
   - `action_raw_vs_executed_gap` 门槛偏松
2. 主线程动作：
   - 修订 `appendix/A-contracts-and-identifiers.md`
   - 收紧 `05-runtime-safety-and-ops.md` 的 gap 阈值
3. 红队复核结论：`通过`（文档终审通过，可进入实单晋级准备阶段）。

### Round 4（约 23:18-23:22）

1. 加压 A：极端行情场景（跳空、流动性骤降、批量 reject）条款化。
2. 主线程落盘：
   - `08-extreme-scenarios-runbook.md`

### Round 5（约 23:21-23:24）

1. 加压 B：数据异常与时钟漂移条款化。
2. 主线程落盘：
   - `09-data-and-clock-runbook.md`

### Round 6（约 23:23-23:26）

1. 加压 C：账本污染与幂等失效条款化。
2. 主线程落盘：
   - `10-ledger-and-idempotency-runbook.md`

### Round 7（约 23:25-23:27）

1. 汇总 runbook 结构模板。
2. 主线程落盘：
   - `RUNBOOK.md`（统一入口）

### Round 8（约 23:29-23:33）

1. 加压 D：配置漂移与人为误操作条款化。
2. 补充 paper/live 证据边界，防止 paper 结果误用为 live 结论。
3. 主线程落盘：
   - `12-paper-live-evidence-boundary.md`

### Round 9（约 23:32-23:34）

1. 红蓝双方输出风险评分矩阵与工程缓解矩阵。
2. 主线程落盘：
   - `13-risk-mitigation-matrix.md`

### Round 10（约 23:35-23:38）

1. 红蓝双方第 2 轮：红队输出“前 5 个仍可致事故漏洞 + 不可协商修复条款 + 最小测试清单”，蓝队输出“12 条 P0 冻结规则草案”。
2. 主线程动作：进入“有条件通过”修订轮。

### Round 11（约 23:38-23:40）

1. 红队第 3 轮裁决：`有条件通过`，提出 5 条必须补丁：
   - 三时钟一致性（500ms）
   - `gap > 0.15` 样本隔离
   - 评审窗口 `invalid_slot_ratio <= 5%`
   - 模拟器校准适用域绑定
   - 5-slot 执行恶化硬停
2. 蓝队提交 `P0-FREEZE` 结构化终稿（可直接粘贴）。
3. 主线程动作：立即落盘补丁并生成独立封版文件。

### Round 12（约 23:40-23:44）

1. 主线程落盘：
   - `P0-FREEZE.md`
   - `05-runtime-safety-and-ops.md`（短窗硬停、样本隔离）
   - `06-simulator-ab-and-promotion.md`（校准适用域、有效交易日门槛）
   - `appendix/A-contracts-and-identifiers.md`（三时钟一致性与字段）
2. 主线程动作：准备午夜前红队最终签字。

### Round 13（约 23:44-23:47）

1. 红队签字：`通过`。
2. 蓝队一致性复核发现 3 处冲突（gap 阈值、模拟器校准表达、`first_fill_ts` 约束）。
3. 主线程动作：立即做最小冲突修复并继续终审。

### Round 14（约 23:47-23:50）

1. 双方最终签字：红队 `通过`，蓝队 `可封版`。
2. 双方提交阶段一交接包（残余风险、冻结约束、第二阶段深挖方向）。
3. 主线程落盘：
   - `appendix/D-phase1-handoff-20260323.md`

### Round 15（约 23:50-23:54）

1. 红队补充“开盘前 30 分钟最易击穿 5 场景”。
2. 蓝队补充“开盘前 30 分钟 5 套快速响应 playbook”。
3. 主线程落盘：
   - `14-pre-open-30min-playbook.md`

### Round 16（约 23:54-23:57）

1. 红蓝双方提交“给新专家的高压问题清单”（红队偏研究拷问，蓝队偏工程验收）。
2. 主线程落盘：
   - `appendix/E-phase2-question-bank-20260323.md`

### Round 17（约 23:57-23:59）

1. 主线程预构建第二阶段任务简报（00:00-02:00），固化目标、硬约束、必答问题与输出格式。
2. 主线程落盘：
   - `15-phase2-deep-work-brief.md`

## 结果快照

1. 文档结构从单文件重构为多层多文件蓝图。
2. 红队对“文档层”终审已给 `通过`。
3. 当前允许推进：
   - `M0/M1` 实施
   - 实单晋级准备（前提是门禁逐项满足）

## 阶段二（00:00-02:00）新双专家深挖

### Round 18（00:00-00:05）

1. 主线程在 `2026-03-24 00:00` 关闭旧专家（Bacon/Arendt）。
2. 新招两位 fresh mind 专家：`Godel`（研究/RL）与 `Bohr`（工程/交付）。
3. 发放统一任务简报与质询清单，进入长考。

### Round 19（00:05-00:13）

1. 两位专家半程回传 `Top5` 高危缺口。
2. 共同结论：先补分钟级骨架（ledger/幂等/单写/因果审计/reward归因），否则后续优化无稳定基础。

### Round 20（00:13-00:25）

1. 发起交叉审查：研究专家评估工程 `Top5`，工程专家评估研究 `Top5`。
2. 得到两周可工程化主线与延期建议。

### Round 21（00:22-00:26）

1. 双方提交完整稿：`Top12` 缺口 + 分包计划（W1-W8 / S1-S8）+ 防错约束。
2. 主线程完成第三轮裁决请求（Now/Next/Later 与 Day1-Day10）。

### Round 22（00:26-00:27）

1. 合并落盘：
   - `16-phase2-consensus-plan.md`
   - `17-day1-day10-sprint-checklist.md`
2. 主线程继续维持心跳监督，准备第四轮挑刺与收敛。

### Round 23（00:27-00:28）

1. 第四轮深挖：研究侧输出 8 个隐藏耦合点与断耦措施；工程侧输出 8 个失败模式与自动化防爆栅栏。
2. 工程侧追加“上线前一日检查单”15 条。
3. 主线程落盘：
   - `18-coupling-and-failure-audit.md`
   - `19-prelaunch-day-checklist.md`

### Round 24（00:28-00:29）

1. 第五轮收敛：两位新专家分别提交“到 02:00 必须冻结的 10 条决策 + 明确不做项 + 资源减半最小闭环”。
2. 主线程落盘：
   - `20-0200-freeze-decisions.md`

### Round 25（00:29-00:36）

1. 新专家补充 owner 级任务矩阵与研究验收矩阵。
2. 主线程落盘：
   - `21-owner-task-matrix-day1-day10.md`
   - `22-research-acceptance-matrix.md`

### Round 26（00:36-00:44）

1. 新专家输出研究/工程双追踪矩阵（冻结决策 -> 证据 -> 脚本/CI -> 运行门禁 -> 回滚）。
2. 主线程落盘：
   - `23-research-traceability-matrix.md`
   - `24-engineering-traceability-matrix.md`

### Round 27（00:44-00:49）

1. 新专家终审 QA 抓出 S0/S1 冲突（reward 键定义、OOD 冻结阈值、fill_rule 语义、晋级口径、关键路径遗漏等）。
2. 主线程完成最小补丁闭环，修订了核心章节并新增配置变更 runbook。

### Round 28（00:49-00:56）

1. 双专家复验：工程侧确认无 S0/S1 阻断；研究侧补充 3 个 S1 细化点（`norm_asof` 追踪、校准样本下限追踪、恢复状态机研究验收项）。
2. 主线程完成追加补丁，更新研究/工程追踪矩阵与研究验收矩阵。

### Round 29（00:56-01:05）

1. 新增独立 RL 专家审查（仅分析可运行性，不做实现）。
2. 结论：`有条件可跑`；`Bandit + white-box` 可开跑，`IQL + SAC` 需先补状态/离线数据/transition 语义契约与样本口径冻结。
3. 主线程落盘：
   - `26-state-observation-contract.md`
   - `27-offline-dataset-contract.md`
   - `28-transition-episode-semantics.md`
4. 同步修订主线文档：
   - `03-algorithm-strategy.md`（SAC 首发作用域）
   - `06-simulator-ab-and-promotion.md`（effective_day 与 paired bootstrap 冻结）
   - `16-phase2-consensus-plan.md`、`17-day1-day10-sprint-checklist.md`、`19-prelaunch-day-checklist.md`、`20-0200-freeze-decisions.md`、`plan.md`。
