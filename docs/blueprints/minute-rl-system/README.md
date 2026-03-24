# 分钟级 RL 子系统蓝图（多文件版）

更新时间：2026-03-24（Asia/Shanghai）

## 阅读顺序

1. [目标与边界](01-goals-and-boundary.md)
2. [系统架构与复用映射](02-system-architecture.md)
3. [算法路线与动作设计](03-algorithm-strategy.md)
4. [奖励函数与可训练性](04-reward-and-trainability.md)
5. [运行门禁与运维安全](05-runtime-safety-and-ops.md)
6. [模拟器、A/B 与晋级规则](06-simulator-ab-and-promotion.md)
7. [里程碑与交付清单](07-roadmap-and-deliverables.md)
8. [极端场景 Runbook](08-extreme-scenarios-runbook.md)
9. [数据异常与时钟漂移 Runbook](09-data-and-clock-runbook.md)
10. [账本污染与幂等失效 Runbook](10-ledger-and-idempotency-runbook.md)
11. [P0 午夜封版条款](P0-FREEZE.md)
12. [统一 Runbook 总入口](RUNBOOK.md)
13. [24:00 封版检查单](11-midnight-freeze-checklist.md)
14. [Paper 与 Live 证据边界](12-paper-live-evidence-boundary.md)
15. [风险与缓解矩阵](13-risk-mitigation-matrix.md)
16. [开盘前 30 分钟压力与响应](14-pre-open-30min-playbook.md)
17. [第二阶段深度优化任务简报](15-phase2-deep-work-brief.md)
18. [第二阶段共识执行计划](16-phase2-consensus-plan.md)
19. [Day1-Day10 冲刺清单](17-day1-day10-sprint-checklist.md)
20. [隐藏耦合与失败模式审计](18-coupling-and-failure-audit.md)
21. [上线前一日检查单](19-prelaunch-day-checklist.md)
22. [02:00 冻结决策](20-0200-freeze-decisions.md)
23. [Owner 任务矩阵（Day1-Day10）](21-owner-task-matrix-day1-day10.md)
24. [研究验收矩阵](22-research-acceptance-matrix.md)
25. [研究可追踪矩阵](23-research-traceability-matrix.md)
26. [工程可追踪矩阵](24-engineering-traceability-matrix.md)
27. [配置漂移与变更控制 Runbook](25-config-and-change-runbook.md)
28. [状态观测契约](26-state-observation-contract.md)
29. [离线训练数据契约](27-offline-dataset-contract.md)
30. [Transition/Episode 语义契约](28-transition-episode-semantics.md)

## 附录

1. [契约冻结与唯一键定义](appendix/A-contracts-and-identifiers.md)
2. [红蓝对抗评审决议](appendix/B-review-decisions.md)
3. [主线程监督日志（2026-03-23）](appendix/C-supervision-log-20260323.md)
4. [阶段一交接包（2026-03-23）](appendix/D-phase1-handoff-20260323.md)
5. [第二阶段质询清单（2026-03-23）](appendix/E-phase2-question-bank-20260323.md)

## 说明

1. 本蓝图替代“单大文件”方案，后续增量更新优先改对应章节，不再把所有内容强塞进一个文件。
2. 兼容历史链接：[plan.md](plan.md) 现在是索引入口而非完整正文。
