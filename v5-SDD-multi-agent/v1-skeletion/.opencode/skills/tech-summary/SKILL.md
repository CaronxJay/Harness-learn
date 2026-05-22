---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# 技术深度分析总结技能

## 使用场景

- 对 `knowledge/raw/` 目录中的原始采集数据（GitHub Trending、Hacker News 等）进行深度分析
- 为每一条技术条目生成精炼摘要、技术亮点、综合评分，并识别跨项目的宏观趋势
- 输出结构化分析结果，支撑整理 Agent 的审核与分发环节

## 执行步骤

### 第 1 步：读取最新采集文件

使用 `Glob` 匹配 `knowledge/raw/*.json`，按文件名中的日期降序排列，取最新的 1-3 个文件。使用 `Read` 逐个读取并解析 JSON。

若 `knowledge/raw/` 目录为空，终止流程并报告「无原始数据，请先执行采集流程」。

### 第 2 步：逐条深度分析

对每条 `items` 中的项目，按以下维度产出分析结果：

#### 2.1 中文摘要

用一句话概括项目核心内容，长度不超过 50 字。表述公式：

> **项目名** + 核心能力（1 短句） + 一句话定位其独特价值

#### 2.2 技术亮点

列出 2-3 个技术亮点，每个亮点必须：

- 用事实说话（引用具体技术选型、架构设计、性能数据）
- 不得使用空洞赞誉词（如"非常强大"、"极其优秀"、"革命性"）
- 示例：「使用 Rust 重写推理引擎，Token 吞吐量比 vLLM 提升 40%」

#### 2.3 综合评分

给出 1-10 的整数评分，并附一句话理由。评分标准：

| 分数区间 | 含义                                 |
| -------- | ------------------------------------ |
| 9-10     | 改变格局：可能重塑领域技术路线       |
| 7-8      | 直接有帮助：可立即用于生产或研究     |
| 5-6      | 值得了解：有亮点但落地尚早或场景窄   |
| 1-4      | 可略过：同质化严重或无明显增量价值   |

**硬性约束**：每批分析（15 个项目以内）中，评分 9-10 的项目不得超过 2 个。若超过，重新审视评分，从严判断。

#### 2.4 标签建议

根据项目内容，建议 3-5 个分类标签，从以下标签池中选取（可建议新标签，但需在趋势发现中说明）：

`llm`、`agent`、`multimodal`、`rag`、`open-source`、`fine-tuning`、`embedding`、`vector-db`、`inference`、`tool-use`、`evaluation`、`safety`、`alignment`、`prompt-engineering`、`reasoning`、`code-generation`、`workflow`、`framework`、`benchmark`、`dataset`、`deployment`、`vision`、`audio`、`robotics`

### 第 3 步：趋势发现

汇总本批所有分析结果，识别宏观趋势（2-5 条），每条趋势包含：

- **趋势主题**：一句话概括（如「推理引擎从 Python 向 Rust/C++ 迁移加速」）
- **涉及项目**：列出相关的项目名（2 个及以上方可构成趋势）
- **新概念标注**：若趋势中包含标签池未覆盖的新概念，明确标注

趋势发现必须基于本批数据，不得凭空捏造。若本批项目间无明显共性，可输出空数组。

### 第 4 步：输出分析结果 JSON

将分析结果写入 `knowledge/articles/tech-summary-YYYY-MM-DD.json`，其中 `YYYY-MM-DD` 为分析日期。

文件名示例：`knowledge/articles/tech-summary-2026-05-05.json`

## 注意事项

- **评分从严**：9-10 分是"改变格局"级别，绝大多数优秀项目应落在 6-8 分区间
- **事实驱动**：技术亮点必须引用可验证信息（README、论文、性能报告），不可凭空推测
- **摘要克制**：50 字硬限制，不堆砌关键词，优先说清楚"做什么"而非"用了什么"
- **标签一致性**：首选标签池中的标签，新增标签需要充足理由并在趋势发现中标注
- **时间戳**：所有时间字段使用 UTC 时区、ISO 8601 格式

## 输出格式

```json
{
  "source": "tech-summary",
  "analyzed_at": "2026-05-05T08:30:00Z",
  "input_files": [
    "knowledge/raw/github-trending-2026-05-05.json"
  ],
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "项目名：一句话概括核心功能。一句话定位其独特价值。",
      "highlights": [
        "使用 Rust 重写推理引擎，Token 吞吐量比 vLLM 提升 40%",
        "支持千卡级分布式推理，线性加速比达 92%"
      ],
      "score": 8,
      "score_reason": "推理性能提升显著且可直接替换现有方案，但生态尚未成熟。",
      "tags": ["llm", "inference", "deployment"]
    }
  ],
  "trends": [
    {
      "topic": "推理引擎从 Python 向 Rust/C++ 迁移加速",
      "projects": ["owner/rust-llm", "owner/cpp-inference"],
      "new_concepts": []
    }
  ]
}
```

| 字段                       | 类型            | 说明                                 |
| -------------------------- | --------------- | ------------------------------------ |
| `source`                   | `str`           | 固定值 `"tech-summary"`              |
| `analyzed_at`              | `str` (ISO)     | 分析完成时间戳（UTC）                |
| `input_files`              | `list[str]`     | 本次分析的原始数据文件路径           |
| `items`                    | `list[dict]`    | 分析结果列表                         |
| `items[].name`             | `str`           | 项目全名（owner/repo）               |
| `items[].url`              | `str`           | 项目链接                             |
| `items[].summary`          | `str`           | 中文摘要（≤50 字）                   |
| `items[].highlights`       | `list[str]`     | 技术亮点（2-3 条，事实驱动）         |
| `items[].score`            | `int`           | 综合评分（1-10），9-10 分每批不超过 2 个 |
| `items[].score_reason`     | `str`           | 评分理由（一句话）                   |
| `items[].tags`             | `list[str]`     | 分类标签（3-5 个）                   |
| `trends`                   | `list[dict]`    | 宏观趋势列表（可为空数组）           |
| `trends[].topic`           | `str`           | 趋势主题                             |
| `trends[].projects`        | `list[str]`     | 涉及的项目名（≥2）                   |
| `trends[].new_concepts`    | `list[str]`     | 新概念（标签池未覆盖的，可为空）     |
