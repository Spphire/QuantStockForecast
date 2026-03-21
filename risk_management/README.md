# Risk Management

`risk_management` 负责把模型预测转换成带约束的组合决策。

## 为什么单独拆出来

这个项目的核心原则之一是：

- 模型输出 `signal`
- 风控和组合层决定是否买、买多少、何时减仓

这样做有几个好处：

- 更容易解释策略行为
- 更容易做风险约束
- 更方便跨模型复用
- 更接近真实量化研究流程

## 当前结构

- [common/README.md](C:/Users/Apricity/Desktop/股票/risk_management/common/README.md)
  预留的共享能力层
- [white_box/README.md](C:/Users/Apricity/Desktop/股票/risk_management/white_box/README.md)
  当前已实现主线

## 当前已实现能力

- 信号过滤
- 流动性过滤
- 行业与风格分组约束
- 仓位分配
- 平滑加减仓
- 交易成本处理
- 批量场景曲线对比

## 当前推荐定位

这是项目最适合继续深化的层之一，因为它决定了“模型有一点 alpha”之后，最终能不能变成更稳定的组合收益。
