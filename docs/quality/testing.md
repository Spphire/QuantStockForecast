# 质量保障：测试与回归

## 运行测试

全量：

```powershell
pytest
```

按领域分组：

```powershell
pytest tests/test_model_prediction
pytest tests/test_risk
pytest tests/test_apps
pytest tests/test_runtime
```

## 当前测试覆盖重点

- `tests/test_model_prediction/test_multi_expert_cli.py`
  - 多 expert 训练/推理与 ensemble 聚合
  - 风控是否可消费 ensemble 预测
- `tests/test_risk/test_protocols.py`
  - strict 协议参数是否与默认一致
- `tests/test_risk/test_risk_pipeline_strict.py`
  - benchmark、行业中性、流动性过滤、总暴露上限
- `tests/test_apps/*`
  - managed runtime、paper daily、ops、submit、reconciler
- `tests/test_runtime/test_strategy_runtime.py`
  - rebalance date、计划落盘与 latest 同步

## 推荐回归顺序

1. `pytest tests/test_risk`
2. `pytest tests/test_model_prediction/test_multi_expert_cli.py`
3. `pytest tests/test_apps`

当策略配置或执行流程变更时，再补跑全量 `pytest`。

