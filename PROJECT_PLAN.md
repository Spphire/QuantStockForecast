# 股票预测项目计划

## 1. 项目目标

本项目的核心目标是构建一个可持续扩展的股票预测系统，并且在项目结构上尽量模块化、可复用、易扩展。

相比按传统工程方式把所有逻辑混在一起，本项目更适合采用下面这种组织思路：

- 顶层按业务板块拆分
- 每个板块内部再按具体能力拆分
- 重要能力单元可以沉淀为独立 skill

这样做的好处是：

- 每个预测方法相互独立，便于单独迭代
- 数据采集、清洗、处理流程可以独立维护
- 后续扩展新模型或新数据源时不会互相污染
- 适合逐步把重复工作抽象成 skill

## 2. 推荐顶层板块划分

建议整个项目先按三个核心板块来拆：

- `模型预测`
- `数据模块`
- `风险管理`

这是当前阶段最清晰、也更贴近真实量化系统的拆法。

### 2.1 模型预测

这个文件夹专门负责股票预测相关内容。

它的职责包括：

- 不同预测方法的独立实现
- 模型训练
- 模型评估
- 模型推理
- 不同方法之间的效果对比

关键原则是：

- 每一种预测方法单独一个文件夹
- 每种方法尽量做到相互解耦
- 每种方法后续都可以逐步沉淀为一个独立 skill

### 2.2 数据模块

这个文件夹专门负责股票数据相关内容。

它的职责包括：

- 数据拉取
- 数据爬取
- 数据清洗
- 数据标准化
- 数据处理与特征生成

关键原则是：

- 数据获取和数据处理放在同一个板块内统一管理
- 不同数据来源和不同处理流程拆成独立能力单元
- 适合把“拉取数据”和“处理数据”的流程分别沉淀为 skill

### 2.3 风险管理

这个文件夹专门负责把模型输出的 `signal` 转成可执行的候选组合。

它的职责包括：

- 白盒规则过滤
- 流动性约束
- 行业与风格暴露约束
- 仓位分配
- 换手与交易成本控制

关键原则是：

- 风控层不直接依赖某个单独模型内部实现
- 统一消费 `model_prediction` 输出的标准信号格式
- 模型负责给出 `score/confidence/horizon`
- 风控负责决定这些信号是否能进入组合

## 3. 推荐目录结构

建议以如下结构作为项目第一版骨架：

```text
.
├─ 模型预测
│  ├─ LightGBM
│  ├─ XGBoost
│  ├─ CatBoost
│  ├─ LSTM
│  ├─ Transformer
│  └─ 公共组件
├─ 数据模块
│  ├─ 数据拉取
│  ├─ 网络爬虫
│  ├─ 数据清洗
│  ├─ 特征工程
│  └─ 公共组件
├─ 风险管理
│  ├─ 白盒风控
│  └─ 公共组件
├─ data
│  ├─ raw
│  ├─ interim
│  └─ processed
├─ configs
├─ notebooks
├─ tests
└─ docs
```

如果后续考虑更偏代码工程化，也可以使用英文目录：

```text
.
├─ model_prediction
│  ├─ lightgbm
│  ├─ xgboost
│  ├─ catboost
│  ├─ lstm
│  ├─ transformer
│  └─ common
├─ data_module
│  ├─ fetchers
│  ├─ crawlers
│  ├─ cleaning
│  ├─ features
│  └─ common
├─ risk_management
│  ├─ white_box
│  └─ common
├─ data
│  ├─ raw
│  ├─ interim
│  └─ processed
├─ configs
├─ notebooks
├─ tests
└─ docs
```

当前更推荐优先使用英文目录名，原因是：

- 更适合 Python 工程结构
- 更适合脚本导入和路径管理
- 后续接工具链时更稳定

其中 `risk_management/white_box` 建议作为第一版默认风控层，优先落地显式规则，而不是一开始就做黑盒风险模型。

## 4. 模型预测板块设计

模型预测文件夹的重点不是把所有模型写在一起，而是让每一种方法都拥有相对独立的空间。

建议如下：

### 4.1 传统机器学习方法

适合第一阶段先落地的内容：

- `LightGBM`
- `XGBoost`
- `CatBoost`

这些方法适合处理结构化特征，例如：

- 历史收益率
- 均线指标
- 成交量变化
- 波动率
- 财务因子
- 板块或行业信息

建议每个方法单独一个文件夹，例如：

- `model_prediction/lightgbm`
- `model_prediction/xgboost`
- `model_prediction/catboost`

每个方法目录内建议包含：

- 训练脚本
- 推理脚本
- 参数配置
- 评估脚本
- 方法说明

### 4.2 时序深度学习方法

适合作为第二阶段扩展：

- `LSTM`
- `GRU`
- `Transformer`

这些方法更适合对过去 N 天的连续时序数据进行建模。

建议同样保持“一种方法一个文件夹”的结构，例如：

- `model_prediction/lstm`
- `model_prediction/transformer`

### 4.3 公共组件

在模型预测板块中，可以额外保留一个公共目录，存放不同模型都会复用的内容，例如：

- 通用训练接口
- 通用评估函数
- 数据加载器
- 通用指标计算
- 模型对比脚本

这样既能保证每个模型独立，也不会重复写大量公共代码。

## 5. 数据模块设计

数据模块建议按“获取数据”和“处理数据”两个方向继续拆开。

### 5.1 数据拉取

这个部分主要用于从现成接口或开源数据源获取数据。

适合处理的数据包括：

- 历史行情
- 指数数据
- 财务数据
- 板块数据

建议目录例如：

- `data_module/fetchers`

### 5.2 网络爬虫

这个部分主要用于抓取结构化接口不容易获取的数据，例如：

- 公司公告
- 财经新闻
- 研报内容
- 舆情内容

建议目录例如：

- `data_module/crawlers`

### 5.3 数据清洗

这个部分负责将原始数据转成可训练数据，主要包括：

- 去重
- 缺失值处理
- 异常值处理
- 时间对齐
- 字段统一

建议目录例如：

- `data_module/cleaning`

### 5.4 特征工程

这个部分负责生成建模特征，例如：

- 收益率特征
- 均线特征
- 波动率特征
- 成交量特征
- 技术指标
- 文本情绪特征

建议目录例如：

- `data_module/features`

### 5.5 公共组件

数据模块内部也建议保留公共目录，用于放置：

- 数据路径管理
- 通用字段定义
- 数据格式转换工具
- 调度入口

## 6. 风险管理板块设计

风险管理板块建议先从白盒风控开始。

建议目录例如：

- `risk_management/white_box`

推荐包含这些能力单元：

- `signal_guard`
- `liquidity_rules`
- `exposure_rules`
- `position_sizing`
- `risk_pipeline`

推荐做法是让 `model_prediction` 侧输出统一字段，例如：

- `date`
- `symbol`
- `score`
- `confidence`
- `horizon`
- `model_name`

这样无论后面接的是 `lightgbm`、`xgboost`、`catboost`，还是 `lstm/transformer`，白盒风控层都能在不改核心规则的前提下复用。

建议目录例如：

- `data_module/common`

## 6. Skill 化思路

你这个拆法非常适合后续做 skill 化。

建议思路是：

- 模型预测文件夹里的每一种方法，后续都可以独立做成一个 skill
- 数据模块中的“拉取数据”“爬取数据”“清洗数据”“特征工程”也都可以做成 skill

也就是说，未来项目结构可以逐步从“普通文件夹”演进到“skill 化能力单元”。

### 6.1 模型预测板块可拆成的 skill

例如：

- `lightgbm-skill`
- `xgboost-skill`
- `catboost-skill`
- `lstm-skill`
- `transformer-skill`

每个 skill 可以负责：

- 方法说明
- 训练流程
- 推理流程
- 参数建议
- 常见输入输出格式

### 6.2 数据模块可拆成的 skill

例如：

- `stock-fetch-skill`
- `stock-crawler-skill`
- `data-cleaning-skill`
- `feature-engineering-skill`

每个 skill 可以负责：

- 数据来源说明
- 执行步骤
- 脚本入口
- 数据格式约定
- 处理流程说明

### 6.3 Skill 目录建议

如果后续要正式按 skill 组织，建议每个 skill 保持独立目录，结构类似：

```text
lightgbm-skill/
├─ SKILL.md
├─ scripts/
├─ references/
└─ assets/
```

其中：

- `SKILL.md` 负责说明这个 skill 的目标和工作流程
- `scripts/` 放训练或处理脚本
- `references/` 放方法说明、参数说明、数据格式说明
- `assets/` 放模板或辅助资源

## 7. 当前推荐实施顺序

按照你这个板块划分，建议开发顺序调整为：

### 第一阶段

- 先建立 `model_prediction`
- 先建立 `data_module`
- 先把目录结构稳定下来

### 第二阶段

- 在 `data_module/fetchers` 中接入一个可用数据源
- 在 `data_module/cleaning` 中完成最基础的数据清洗
- 在 `data_module/features` 中生成第一版训练特征

### 第三阶段

- 先实现 `model_prediction/lightgbm`
- 跑通训练、验证、预测流程
- 将其作为第一版 baseline

### 第四阶段

- 补充 `model_prediction/xgboost`
- 补充 `model_prediction/catboost`
- 对比不同传统模型效果

### 第五阶段

- 再扩展 `lstm`、`transformer`
- 再考虑把稳定的方法整理成独立 skill

## 8. 当前建议结论

目前最推荐的项目组织方式是：

- 顶层只保留两个主板块：`model_prediction` 和 `data_module`
- 模型预测内部按“每种方法一个文件夹”组织
- 数据模块内部按“拉取、爬虫、清洗、特征工程”组织
- 每个能力单元未来都可以进一步整理为 skill

这个结构比一开始按训练、评估、回测横切拆分更适合你当前这个项目，因为它更直观，也更方便后续逐步沉淀成模块化能力。
