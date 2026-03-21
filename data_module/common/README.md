# Data Common

`data_module/common` 存放数据层的共享约束。目前最核心的文件是：

- [stock_schema.py](C:/Users/Apricity/Desktop/股票/data_module/common/stock_schema.py)

## 核心目标

把不同数据源输出的字段名、日期格式、数值列和排序方式统一起来，让后续模块只面向一种稳定格式工作。

## 当前包含的能力

- 识别中英文别名列名
- 统一列名到项目标准
- 数值列转数值类型
- 日期列转标准日期
- 统一排序为 `symbol + date`
- 提供默认数据目录定位

## 当前标准列

### 必需列

- `date`
- `open`
- `high`
- `low`
- `close`
- `volume`

### 核心列

- `date`
- `symbol`
- `open`
- `high`
- `low`
- `close`
- `volume`

### 可选列

- `amount`
- `turnover`
- `pct_change`
- `price_change`
- `amplitude`
- `provider`
- `adjust`

## 典型调用方式

```python
from data_module.common.stock_schema import normalize_dataframe

normalized = normalize_dataframe(raw_df, provider="akshare-eastmoney", adjust="hfq")
```

## 对下游的意义

- `model_prediction/lightgbm` 假设输入已经基本符合这份 schema
- `predict_lightgbm.py` 也会先做一次 schema 标准化
- 新的数据源只要能适配到这层，就不用改模型训练主线

## 维护建议

- 新增数据源时，优先扩展 alias 映射，而不是在每个训练脚本里写临时列名适配
- 如果未来引入分钟线或更多字段，优先以“向后兼容”的方式扩充 schema
