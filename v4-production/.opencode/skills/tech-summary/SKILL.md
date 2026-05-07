---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# tech-summary — 技术内容深度分析技能

## 使用场景

- 对 `knowledge/raw/` 下的原始采集数据进行深度分析与总结
- 从技术动态中提炼关键洞察与趋势信号
- 为下游知识入库与分发提供高质量的结构化分析结果

## 执行步骤

### 第 1 步：读取最新采集文件

- 使用 Glob 扫描 `knowledge/raw/` 下按日期排序的最新文件（`github-trending-*.json` 等）
- 解析 JSON，提取 `items` 数组作为分析输入
- 校验数据完整性：确保 `name`、`url`、`summary`、`stars` 等必填字段非空

### 第 2 步：逐条深度分析

对每一条原始条目进行四维度分析：

**a) 中文摘要（≤50 字）**

在原始 summary 基础上进一步压缩提炼，保留核心信息：
```
摘要 = 一句话说清楚项目是什么 + 解决了什么关键问题
```
- 不编造能力或性能数据
- 不确定处标注「（信息不详）」
- 示例：`开源通才 Agent 框架，支持多工具调用与自主任务执行，社区反响热烈。`

**b) 技术亮点（2-3 个）**

每个亮点必须基于事实，不使用主观溢美之词：

| 亮点类型 | 示例 |
|----------|------|
| 架构创新 | 「用 actor 模式解耦工具调用与推理循环」 |
| 性能突破 | 「token 消耗比同类方案降低 40%（来源 README）」 |
| 实用价值 | 「一行命令完成本地私有知识库部署」 |
| 社区信号 | 「发布 3 天获 5000+ stars」 |

**c) 相关度评分（1-10）**

| 分数区间 | 含义 | 典型场景 | 占比约束 |
|----------|------|----------|----------|
| **9-10** | 改变格局 | 重大突破性技术、颠覆性框架发布、范式级创新 | **≤ 2 个** |
| **7-8** | 直接有帮助 | 可立刻落地的高质量工具、生产级实践、深度技术文章 | 不限 |
| **5-6** | 值得了解 | 有一定参考价值的新项目、入门教程、行业动态 | 不限 |
| **1-4** | 可略过 | 与 AI/Agent 关联微弱、纯营销内容、信息量极低 | 不限 |

> 每条评分必须附带 **1-2 句评分理由**（`score_reason`），说明为何给出该分数。

**d) 标签建议（3-5 个）**

- 优先使用已有标签库中的标签
- 每个标签 ≤ 20 字符，使用 snake_case
- 标签应覆盖：技术领域、应用场景、项目特性

### 第 3 步：趋势发现

对当日采集的所有项目进行横向归纳：

**a) 共同主题识别**

找出当日条目中反复出现的技术关键词或模式，总结为 1-3 个共同主题：
```
示例：
- 「Agent 框架爆发」：本周出现 5 个 Agent 框架项目，均以多工具编排为核心
- 「RAG 轻量化趋势」：多个项目聚焦百行代码级 RAG 实现
```

**b) 新概念捕获**

标记当日首次出现的新技术术语、项目模式或行业概念：
```
示例：
- 「Model Context Protocol (MCP)」首次在 trending 中出现，3 个项目提及
```

**c) 热度对比**

简要对比当日数据与近期趋势的差异（若历史数据可用）：
```
示例：
- 本周 Agent 框架类项目占比 33%，较上周上升 12%
```

### 第 4 步：输出分析结果 JSON

将完整分析结果写入 `knowledge/raw/tech-summary-YYYY-MM-DD.json`。

---

## 注意事项

- 摘要严格 ≤50 字，超出需再压缩
- 技术亮点每条需标注信息来源（`source: readme` / `source: description` / `source: 推断`）
- `9-10 分`不得放水，当日 15 个项目中最多 2 个获此评分
- 若合格条目不足 15 个，有多少分析多少，不凑数
- 评分理由必须具体，禁止使用「感觉不错」「挺有意思」等模糊表述
- 趋势发现基于事实归纳，不凭空推测

---

## 输出格式

```json
{
  "source": "tech-summary",
  "skill": "tech-summary",
  "analyzed_at": "2026-05-06T14:00:00+08:00",
  "input_file": "knowledge/raw/github-trending-2026-05-06.json",
  "stats": {
    "total_items": 15,
    "avg_score": 6.4,
    "score_9_10_count": 1,
    "score_7_8_count": 6,
    "score_5_6_count": 7,
    "score_1_4_count": 1
  },
  "trends": {
    "themes": [
      {
        "theme": "Agent 框架爆发",
        "description": "当日出现 5 个 Agent 相关框架项目，均以多工具编排、自主任务执行为核心能力。",
        "related_items": [
          "mannaandpoem/OpenManus",
          "other/agent-framework-2"
        ]
      }
    ],
    "new_concepts": [
      {
        "concept": "Model Context Protocol (MCP)",
        "description": "由 Anthropic 提出的模型与外部工具交互协议，首次在 trending 中由 2 个项目提及。"
      }
    ]
  },
  "items": [
    {
      "name": "mannaandpoem/OpenManus",
      "url": "https://github.com/mannaandpoem/OpenManus",
      "summary": "开源通才 Agent 框架，支持多工具调用与自主任务执行，社区一周内获万星关注。",
      "highlights": [
        "用模块化架构解耦 LLM 后端与工具链（source: readme）",
        "发布一周获 12k+ stars，社区反响极佳（source: description）"
      ],
      "relevance_score": 9,
      "score_reason": "通才 Agent 框架是当前最活跃的技术赛道，该项目设计完整、社区反响热烈，有成为赛道标杆的潜力。",
      "tags": ["agent-framework", "llm", "open-source", "tool-calling", "multi-modal"],
      "stars": 12400
    }
  ]
}
```

**顶层字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | 是 | 固定值 `tech-summary` |
| `skill` | string | 是 | 固定值 `tech-summary` |
| `analyzed_at` | datetime | 是 | 分析时间，ISO 8601，UTC+8 |
| `input_file` | string | 是 | 所分析的原始采集文件路径 |
| `stats` | object | 是 | 评分分布统计 |
| `trends` | object | 是 | 趋势发现结果 |
| `items` | array | 是 | 分析后的条目列表 |

**stats 字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `total_items` | int | 是 | 分析的总条目数 |
| `avg_score` | float | 是 | 平均相关度评分 |
| `score_9_10_count` | int | 是 | 9-10 分条目数 |
| `score_7_8_count` | int | 是 | 7-8 分条目数 |
| `score_5_6_count` | int | 是 | 5-6 分条目数 |
| `score_1_4_count` | int | 是 | 1-4 分条目数 |

**items 字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 项目名称 |
| `url` | string | 是 | 项目链接 |
| `summary` | string | 是 | 中文摘要，≤50 字 |
| `highlights` | string[] | 是 | 技术亮点，2-3 个，每条标注信息来源 |
| `relevance_score` | int | 是 | 相关度评分 1-10 |
| `score_reason` | string | 是 | 评分理由，1-2 句话 |
| `tags` | string[] | 是 | 标签建议，3-5 个 |
| `stars` | int | 是 | Star 数量 |

**trends 字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `themes` | array | 是 | 共同主题列表，每项含 `theme`、`description`、`related_items` |
| `new_concepts` | array | 否 | 新概念列表，每项含 `concept`、`description` |
