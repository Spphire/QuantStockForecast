# Execution Common

`execution/common` 存放执行层的共享数据结构和无券商依赖的逻辑。

## 当前文件

- [execution_models.py](C:/Users/Apricity/Desktop/股票/execution/common/execution_models.py)
  统一的数据结构
- [broker_interface.py](C:/Users/Apricity/Desktop/股票/execution/common/broker_interface.py)
  券商接口抽象
- [order_safety.py](C:/Users/Apricity/Desktop/股票/execution/common/order_safety.py)
  订单前的白盒安全校验
- [reconciliation.py](C:/Users/Apricity/Desktop/股票/execution/common/reconciliation.py)
  目标仓位和实际持仓的对账、订单意图生成

## 当前定位

这层的目标是把“策略逻辑”和“券商适配器”解耦。  
只要后面再接别的 broker，理论上都应该优先复用这一层。
