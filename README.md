# QueryPilot

面向数据库问答的工具调用与自我纠错 Agent。

## 当前状态

**最小执行框架已完成。**当前包含可运行的 Agent Loop、三个只读 SQLite 工具、调用预算、结构化轨迹和一条脚本策略 smoke demo。脚本策略用于验证执行链路，不是 LLM，也没有训练脚本或实验指标。该项目是独立个人项目，不复用 MiniMind / MedSFT 的结果，也不代表公司实习交付。

## 项目目标

实现一个能够查看数据库结构、执行只读 SQL、读取反馈并修正查询的轻量 Agent。先建立可靠的执行与评测闭环，再探索轨迹 SFT 和 GRPO 能否改善任务成功率与执行成本。

```text
问题 + 数据库
    -> 模型决策
    -> list_tables / get_schema / execute_sql
    -> 结果或错误反馈
    -> 修正查询或结束任务
    -> 保存轨迹与评测
```

第一版使用 Python 执行循环，不依赖 LangGraph。不从零实现 RL 训练系统；训练后端待接口验证后确定。

## 目录

```text
querypilot/
├── README.md
├── docs/PLAN.md
├── pyproject.toml
├── src/querypilot/
│   ├── core.py        # Agent Loop 与 SQLite 工具
│   └── __main__.py    # 可重复的脚本策略演示
└── tests/test_core.py
```

模型、数据库、数据集、轨迹和训练产物不进入 Git；对应路径已加入 `.gitignore`。小型公开测试夹具可在后续审查来源后单独提交。

## 运行最小 Demo

不需要第三方依赖或 GPU：

```bash
PYTHONPATH=src python3 -m querypilot --demo
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

演示会创建临时商品数据库。脚本策略依次查看表、查看 schema、故意使用不存在的字段，接收错误后修正 SQL，最终返回销售额最高的商品。它验证的是：

```text
policy -> tool call -> validated execution -> observation -> next decision -> final answer
```

## 当前边界与下一步

- `policy(messages, tool_schemas)` 是唯一模型接入点，下一阶段替换为支持工具调用的真实 LLM provider。
- `execute_sql` 同时使用 SQL 类型检查和 SQLite `mode=ro` / `query_only`；当前超时依赖 SQLite progress handler，尚未做进程级硬隔离。
- 当前数据库为合成 smoke fixture，不是公开训练或评测数据。
- 尚未实现任务评测、轨迹 SFT 或 GRPO，不能写训练提升。

下一步按 [实施计划](docs/PLAN.md) 选择公开数据并建立小规模基线。此阶段仍不需要 GPU。
