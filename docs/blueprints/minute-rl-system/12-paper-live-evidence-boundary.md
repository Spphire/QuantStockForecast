# 12 Paper 与 Live 证据边界

## 1. 总原则

1. `paper` 结果只用于研究、回放、shadow 与工程稳定性验证。
2. `paper` 结果不得直接推导 `live-ready` 结论。
3. 所有引用 `paper` 结果的文档必须带明确免责声明。

## 2. 禁止误用

以下结论禁止仅基于 `paper` 得出：

1. 已具备真实账户上线条件。
2. 真实成交质量已验证。
3. 真实滑点/拒单成本已验证。
4. 真实资金承载能力已验证。

## 3. 强制免责声明

统一中文模板：

`结论基于 paper 环境，不代表 live 成交、滑点、资金承载与市场冲击条件已经验证。`

## 4. 晋级制度约束

1. paper 通过只表示可进入下一层验证，不表示可直接 live。
2. `paper -> live candidate` 前必须补齐：
   - 执行差异分析
   - 滑点偏差分析
   - 市场冲击假设审查
   - 账户级风控审查

## 5. 报告与看板约束

1. paper dashboard 必须显示 `PAPER ONLY`。
2. 报告需字段：
   - `evidence_scope`
   - `environment_type`
   - `simulator_version`
   - `live_validation_status`
   - `scope_disclaimer_present`
3. 若 `environment_type=paper` 且 `scope_disclaimer_present=false`，该报告无效。

## 6. Fail-Fast

1. 一旦发现把 paper 结论写成 live-ready，立即撤回并更正。
2. 相关评审结论标记为 `invalid_due_to_scope_misuse`。
