# 快速开始

本页给出当前项目最短可用路径：`数据 -> 预测 -> 风控 -> 执行`。

## 1. 环境准备

在仓库根目录执行：

```powershell
python -m pip install -e .
python -m pip install -e .[dev]
```

Alpaca 凭据二选一：

1. 环境变量：`<PREFIX>_API_KEY` / `<PREFIX>_SECRET_KEY` / `<PREFIX>_BASE_URL`  
2. 本地文件：`configs/alpaca_accounts.local.json`

项目默认常见前缀：

- `ALPACA_ZERO_SHOT`
- `ALPACA_US_FULL`

## 2. 跑研究侧（生成风险目标仓位）

推荐直接用 Windows 包装脚本（已包含时间窗检查与完整流水线）：

```powershell
powershell -ExecutionPolicy Bypass -File .\execution\scripts\windows\invoke_daily_research_pipeline.ps1 -IgnoreTimeWindow
```

完成后重点检查：

- `risk_management/white_box/runtime/us_zeroshot_a_share_multi_expert_daily/risk_summary.json`
- `risk_management/white_box/runtime/us_full_multi_expert_daily/risk_summary.json`

## 3. 跑执行侧（Paper Trading）

先做健康检查：

```powershell
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json healthcheck
```

再做 dry-run：

```powershell
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json run
```

确认后再提交到 paper 账户：

```powershell
python -m execution.managed.apps.paper_daily execution/strategies/us_zeroshot_a_share_multi_expert_daily.json run --submit --require-paper
```

查看最近一次运行摘要：

```powershell
python -m execution.managed.apps.paper_ops execution/strategies/us_zeroshot_a_share_multi_expert_daily.json latest-run
```

## 4. 常见输出位置

- 研究产物：`model_prediction/*/artifacts/*`
- 风控产物：`risk_management/white_box/runtime/<strategy>/`
- 执行运行时：`execution/runtime/<strategy>/`
- 执行状态：`execution/state/<strategy>/`
- 账本：`artifacts/paper_trading/<strategy>/paper_ledger.sqlite3`

