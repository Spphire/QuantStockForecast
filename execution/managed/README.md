# Managed Execution Runtime

`execution.managed` 是这份仓库里的产品级执行运行时。

它的职责不是重新实现 `multi-expert` 研究链路，而是把研究产物安全地运行起来：

- 消费 `risk_management/white_box` 产出的目标仓位 bundle
- 执行 preflight、session guard、broker-aware risk gate
- 维护 paper/live 运行时 ledger、healthcheck、ops shell
- 对接 Alpaca broker，并把提交结果、recovery、reconciliation 持久化

## 边界

这层和仓库其余模块的推荐边界如下：

- `model_prediction/*`
  负责 expert 与 ensemble 预测
- `risk_management/white_box/*`
  负责组合目标、调仓动作与风控摘要
- `execution/common/*`
  负责通用执行模型、对账、计划构建与状态写盘
- `execution/alpaca/*`
  负责 Alpaca broker 适配
- `execution/managed/*`
  负责产品化 runtime、日常运维入口和审计能力

## 入口

推荐直接使用模块入口：

```powershell
python -m execution.managed.apps.run_multi_expert_paper execution/strategies/us_zeroshot_a_share_multi_expert_daily.json
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json run
python -m execution.managed.apps.paper_smoke execution/strategies/us_zeroshot_a_share_multi_expert_daily.json
python -m execution.managed.apps.paper_ops execution/strategies/us_zeroshot_a_share_multi_expert_daily.json latest-run
```

`execution/scripts/*.py` 仍然保留为薄包装，方便已有调度器继续调用，但默认心智模型应该是 `execution.managed`。
