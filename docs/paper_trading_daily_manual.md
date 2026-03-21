# 每日调仓 Paper 实战操作手册

## 1. 目标

这份手册用于把当前项目推进到 **双账户美股 paper trading**：

- 账户 A：`A股训练 -> 美股 zero-shot`
- 账户 B：`美股全量训练 -> 美股本地模型`

目标不是一上来就 live，而是先把：

- 开户
- API key 配置
- 每日推理
- 每日风险过滤
- 每日目标仓位生成
- paper 下单

这整条链路跑顺。

## 2. 先开什么账户

### 当前建议

先开 `2 个 Alpaca paper account`：

- `paper_a`: `ALPACA_ZERO_SHOT`
- `paper_b`: `ALPACA_US_FULL`

截至 `2026-03-21`，Alpaca 官方文档说明：

- `Paper Only Account` 全球可开：[Paper Trading](https://docs.alpaca.markets/docs/trading/paper-trading/)
- `Live Account` 需要正式 brokerage onboarding：[Account Plans](https://docs.alpaca.markets/docs/account-plans)

### 现在不要先做的事

- 不要先开两个 live account
- 不要先上保证金、做空、盘前盘后
- 不要先做高频和盘中重平衡

## 3. 开户需要什么

### Paper

Paper 一般只需要：

- 邮箱
- Alpaca 控制台账号

然后在控制台里新建 paper account 并生成对应 API keys。

### Live

如果以后你要申请 live，官方账户/KYC 文档里通常会涉及：

- 姓名
- 出生日期
- 住址
- 身份识别号码
- 联系方式
- 税务居民信息

官方参考：

- [Create Account](https://docs.alpaca.markets/reference/createaccount)
- [Broker API Getting Started](https://docs.alpaca.markets/v1.3/docs/getting-started-with-broker-api)
- [CIP](https://docs.alpaca.markets/reference/post-v1-accounts-account_id-cip)
- [International Accounts](https://docs.alpaca.markets/docs/international-accounts)

## 4. 项目里现在已经准备好的策略

### 实验对比策略

- [us_zeroshot_a_share_regression_balanced.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_zeroshot_a_share_regression_balanced.json)
- [us_full_regression_balanced.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_full_regression_balanced.json)

这两份主要用于比较历史回测和生成 dry-run 计划。

### 日常实战策略

- [us_zeroshot_a_share_daily.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_zeroshot_a_share_daily.json)
- [us_full_daily.json](C:/Users/Apricity/Desktop/股票/execution/strategies/us_full_daily.json)

这两份才是建议你后面每天运行时使用的配置。

## 5. API Key 配置

参考模板：

- [execution/alpaca/.env.example](C:/Users/Apricity/Desktop/股票/execution/alpaca/.env.example)
- 本地配置文件：
  [alpaca_accounts.local.json](C:/Users/Apricity/Desktop/股票/configs/alpaca_accounts.local.json)

建议你分别把两个 paper account 的 key 配成这 6 个环境变量：

- `ALPACA_ZERO_SHOT_API_KEY`
- `ALPACA_ZERO_SHOT_SECRET_KEY`
- `ALPACA_ZERO_SHOT_BASE_URL=https://paper-api.alpaca.markets`
- `ALPACA_US_FULL_API_KEY`
- `ALPACA_US_FULL_SECRET_KEY`
- `ALPACA_US_FULL_BASE_URL=https://paper-api.alpaca.markets`

### PowerShell 临时配置

```powershell
$env:ALPACA_ZERO_SHOT_API_KEY="你的paper_a_key"
$env:ALPACA_ZERO_SHOT_SECRET_KEY="你的paper_a_secret"
$env:ALPACA_ZERO_SHOT_BASE_URL="https://paper-api.alpaca.markets"

$env:ALPACA_US_FULL_API_KEY="你的paper_b_key"
$env:ALPACA_US_FULL_SECRET_KEY="你的paper_b_secret"
$env:ALPACA_US_FULL_BASE_URL="https://paper-api.alpaca.markets"
```

### PowerShell 持久化配置

```powershell
[System.Environment]::SetEnvironmentVariable("ALPACA_ZERO_SHOT_API_KEY","你的paper_a_key","User")
[System.Environment]::SetEnvironmentVariable("ALPACA_ZERO_SHOT_SECRET_KEY","你的paper_a_secret","User")
[System.Environment]::SetEnvironmentVariable("ALPACA_ZERO_SHOT_BASE_URL","https://paper-api.alpaca.markets","User")

[System.Environment]::SetEnvironmentVariable("ALPACA_US_FULL_API_KEY","你的paper_b_key","User")
[System.Environment]::SetEnvironmentVariable("ALPACA_US_FULL_SECRET_KEY","你的paper_b_secret","User")
[System.Environment]::SetEnvironmentVariable("ALPACA_US_FULL_BASE_URL","https://paper-api.alpaca.markets","User")
```

设置完成后，重新打开一个 PowerShell 窗口再运行脚本。

### 当前项目的更简便方式

我已经按你的要求把第一组 paper 凭证保存在：

- [alpaca_accounts.local.json](C:/Users/Apricity/Desktop/股票/configs/alpaca_accounts.local.json)

当前执行层会：

1. 优先读环境变量
2. 如果环境变量没配，再自动读取这个本地配置文件

所以你现在后续直接运行脚本即可，不一定要再手动设置环境变量。

注意：

- 这个文件里现在有真实 secret
- 不要把它发给别人
- 如果你以后把项目上传到 GitHub，先删掉它或者把它加入忽略清单

## 6. 每日调仓的推荐节奏

### 结论先说

你可以 **每日调仓**，而且当前系统已经支持这一点。  
实现方式是把白盒风控的 `rebalance_step` 设为 `1`，每天都生成当天的目标仓位。

### 推荐运行节奏

最稳的第一版是：

1. `T日收盘后` 更新数据和信号
2. `T日收盘后` 生成最新目标仓位
3. `T+1日开盘前或开盘后几分钟` 提交订单

如果你人在中国，通常可以这样理解：

- 美股常规收盘后再跑推理
- 下一次美股开盘前或开盘后几分钟执行

不要在同一根日线还没完全稳定时就立即按收盘信号交易。

## 7. 每日运行的完整命令

下面默认你在项目根目录：

`C:\Users\Apricity\Desktop\股票`

建议先激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

然后先定义两个日期变量：

```powershell
$endDate = "2026-03-21"
$endDateCompact = $endDate.Replace("-", "")
```

这里的 `$endDate` 用你当天最新的数据日期替换。

### Step 1: 更新美股股票池数据

```powershell
python data_module/fetchers/scripts/fetch_stock_universe.py --provider stooq --symbols-file configs/stock_universe_us_large_cap_30.txt --name us_large_cap_30 --start 2020-01-01 --end $endDate --continue-on-error
```

### Step 2: 更新元数据

这个不用每天都跑，但建议：

- 第一次运行时跑一次
- 之后每周或每月补一次

```powershell
python data_module/fetchers/scripts/fetch_stock_metadata.py --provider wikipedia_sp500 --symbols-file configs/stock_universe_us_large_cap_30.txt --output-csv data/interim/stooq/universes/us_large_cap_30_metadata.csv
```

### Step 3A: 生成 zero-shot 模型的最新预测

```powershell
python model_prediction/lightgbm/scripts/predict_lightgbm.py data/interim/stooq/universes/us_large_cap_30_20200101_${endDateCompact}_hfq_normalized.csv --model-path model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/model.txt --reference-metrics model_prediction/lightgbm/artifacts/large_cap_50_20200101_20241231_hfq_normalized_regression_5d/metrics.json --output-dir model_prediction/lightgbm/artifacts/us_zeroshot_daily --eval-start 2024-01-01 --eval-end $endDate
```

### Step 3B: 生成美股本地模型的最新预测

```powershell
python model_prediction/lightgbm/scripts/predict_lightgbm.py data/interim/stooq/universes/us_large_cap_30_20200101_${endDateCompact}_hfq_normalized.csv --model-path model_prediction/lightgbm/artifacts/us_large_cap_30_full_regression_5d/model.txt --reference-metrics model_prediction/lightgbm/artifacts/us_large_cap_30_full_regression_5d/metrics.json --output-dir model_prediction/lightgbm/artifacts/us_full_daily --eval-start 2024-01-01 --eval-end $endDate
```

## 8. 每日目标仓位生成

### 账户 A: zero-shot 每日目标仓位

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py model_prediction/lightgbm/artifacts/us_zeroshot_daily/test_predictions.csv --metadata-csv data/interim/stooq/universes/us_large_cap_30_metadata.csv --rebalance-step 1 --top-k 5 --min-score 0 --min-confidence 0.7 --min-close 5 --min-amount 100000000 --group-column industry_group --max-per-group 1 --secondary-group-column amount_bucket --secondary-max-per-group 2 --weighting score_confidence --max-position-weight 0.35 --transaction-cost-bps 10 --output-dir risk_management/white_box/runtime/us_zeroshot_daily
```

### 账户 B: 美股本地模型每日目标仓位

```powershell
python risk_management/white_box/scripts/run_white_box_risk.py model_prediction/lightgbm/artifacts/us_full_daily/test_predictions.csv --metadata-csv data/interim/stooq/universes/us_large_cap_30_metadata.csv --rebalance-step 1 --top-k 5 --min-score 0 --min-confidence 0.7 --min-close 5 --min-amount 100000000 --group-column industry_group --max-per-group 1 --secondary-group-column amount_bucket --secondary-max-per-group 2 --weighting score_confidence --max-position-weight 0.35 --transaction-cost-bps 10 --output-dir risk_management/white_box/runtime/us_full_daily
```

这里最关键的就是：

- `--rebalance-step 1`

这就是“每日调仓”的开关。

## 9. 下单前先 dry-run

### zero-shot

```powershell
python execution/scripts/run_paper_strategy.py execution/strategies/us_zeroshot_a_share_daily.json
```

### us_full

```powershell
python execution/scripts/run_paper_strategy.py execution/strategies/us_full_daily.json
```

生成的关键文件会在：

- `execution/runtime/.../execution_plan.json`
- `execution/runtime/.../target_positions.csv`
- `execution/runtime/.../order_intents.csv`

先看：

- 这次要买哪几只
- 每只目标权重多少
- 有没有异常大单

如果你想看某条策略最近一次运行状态，可以直接执行：

```powershell
python execution/scripts/show_strategy_state.py us_zeroshot_a_share_daily
python execution/scripts/show_strategy_state.py us_full_daily
```

## 10. 确认无误后提交 paper 订单

### zero-shot 提交

```powershell
python execution/scripts/run_paper_strategy.py execution/strategies/us_zeroshot_a_share_daily.json --submit
```

### us_full 提交

```powershell
python execution/scripts/run_paper_strategy.py execution/strategies/us_full_daily.json --submit
```

脚本会：

- 拉 Alpaca 当前账户权益和持仓
- 对比目标仓位
- 生成 order intents
- 做基本安全校验
- 提交 Alpaca paper 订单

并且会自动把记录写到：

- `execution/runtime/<strategy_id>/<timestamp>/`
- `execution/runtime/<strategy_id>/latest/`
- `execution/state/<strategy_id>/latest_state.json`
- `execution/state/<strategy_id>/order_journal.csv`

### 当前默认下单方式

`daily` 策略现在默认不是纯 `qty`，而是更稳的 `hybrid`：

- `buy` 按 `notional`
- `sell` 按 `qty`

同时默认附带：

- `buying_power_buffer=0.97`
- `max_buy_retries=1`
- `buy_retry_shrink_ratio=0.97`

所以如果你在 Alpaca 界面里看到某些买单 `qty` 为空，这通常不是异常，而是因为它是按金额单提交的。  
真实的本地计划仍然会把估算股数写在：

- `execution/runtime/<strategy_id>/latest/order_intents.csv`

而提交过程和即时状态会写在：

- `execution/runtime/<strategy_id>/latest/submission_attempts.json`
- `execution/runtime/<strategy_id>/latest/submitted_order_statuses.json`

## 11. 每日结束后检查什么

建议你每天至少看这几项：

- 最新目标仓位是否合理
- 订单数量是否异常
- 是否有某只股票权重明显过大
- Alpaca 账户里是否出现未成交或部分成交
- 两个账户今天的组合是否开始明显分化

如果你想快速看“上次到底下了什么、状态是什么”，可以直接运行：

```powershell
python execution/scripts/show_strategy_state.py us_zeroshot_a_share_daily
python execution/scripts/show_strategy_state.py us_full_daily
```

你还可以顺手跑这个对比脚本：

```powershell
python execution/scripts/compare_paper_strategies.py execution/strategies/us_zeroshot_a_share_daily.json execution/strategies/us_full_daily.json --output-csv execution/runtime/strategy_comparison_daily.csv
```

## 12. 建议的调度方式

这套系统当前 **不需要 7x24 常驻运行**。

建议你在 Windows 里做两个定时任务：

### 任务 1: 收盘后研究任务

负责：

- 抓最新数据
- 生成两条策略的预测
- 生成两条策略的 `risk_positions.csv`

### 任务 2: 开盘前执行任务

负责：

- 先 dry-run
- 再 `--submit`
- 保存执行日志

## 13. 每周 / 每月要做的事

### 每周建议

- 检查 paper 两个账户的收益、回撤、换手
- 看哪条线的订单行为更稳定

### 每月建议

- 重新抓一遍元数据
- 重新评估 `us_full` 是否需要重训

### 模型重训建议

- `zero-shot` 不需要每天重训
- `us_full` 也不建议每天重训，建议先按 `每周一次` 或 `每月一次`

## 14. 实战第一阶段的硬规则

第一阶段建议你强制遵守：

- 只做 `paper`
- 只做 `US equities`
- 只做 `long-only`
- 只用 `market/day`
- 不开盘前盘后交易
- 不做杠杆
- 不做做空

## 15. 当前最现实的建议

如果你明天就要开始跑：

1. 先开好 `2 个 Alpaca paper account`
2. 配好这 6 个环境变量
3. 先只跑 `dry-run` 1 到 2 天
4. 再打开 `--submit`
5. 连续观察 2 到 4 周

## 16. 当前项目状态提醒

这份手册对应的是 **当前已经落地的 execution MVP**。

也就是说：

- 每日推理可以跑
- 每日白盒风控可以跑
- 每日生成目标仓位可以跑
- Alpaca paper 下单接口也已经接好了

但还没有这些能力：

- websocket 成交回报监听
- 自动补单 / 撤单策略
- 盘中风控熔断
- 真正的一键全流程编排脚本

所以第一阶段请把它当成：

- `半自动、可审阅、可追踪` 的 paper trading 系统

而不是完全无人值守的正式交易系统。
