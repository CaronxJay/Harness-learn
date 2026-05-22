---
name: arxiv-papers
description: 当需要采集 arXiv 最新 AI 领域论文时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# arXiv 论文采集技能

## 使用场景

- 每日自动化采集 arXiv 上 AI/LLM/Agent 领域最新预印本论文
- 为知识库管线提供学术前沿的原始数据输入，与 GitHub Trending、Hacker News 数据互补
- 支撑技术分析 Agent 识别学术趋势与产业落地的交叉点

## 执行步骤

### 第 1 步：构建查询请求

基于以下参数构造 arXiv API 查询 URL：

- **分类范围**：`cs.AI`、`cs.CL`、`cs.LG`、`cs.MA`、`cs.HC`
- **时间范围**：近 3 天提交/更新的论文
- **排序**：按提交时间降序（`sortBy=submittedDate&sortOrder=descending`）
- **数量**：`max_results=100`

URL 模板：

```
http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG+OR+cat:cs.MA+OR+cat:cs.HC&sortBy=submittedDate&sortOrder=descending&max_results=100&start=0
```

**注意**：若 API 返回 HTTP 503（服务过载），等待 30 秒后重试 1 次；仍失败则记录日志并终止。

### 第 2 步：调用 arXiv API

使用 `WebFetch` 工具以 `text` 格式抓取上一步构造的 URL，获取 Atom XML 格式响应。

若响应体超过 `WebFetch` 的默认截断限制，可先用 `max_results=50` 分两批拉取。

### 第 3 步：解析提取字段

从 Atom XML 响应中逐条解析每个 `<entry>`，提取以下字段：

| XML 元素              | 提取为          | 说明                     |
| ---------------------- | --------------- | ------------------------ |
| `<id>`                 | `arxiv_id`      | arXiv 论文 ID（去掉 `http://arxiv.org/abs/` 前缀） |
| `<title>`              | `title`         | 论文标题（去掉首尾空格与换行符） |
| `<summary>`            | `abstract`      | 论文摘要（去掉首尾空格与换行符） |
| `<author>/<name>`      | `authors`       | 作者姓名列表，取前 5 位   |
| `<published>`          | `published`     | 首次提交日期（ISO 8601）  |
| `<updated>`            | `updated`       | 最后更新日期（ISO 8601）  |
| `<category term="..."/>`| `categories`   | arXiv 分类代码列表        |
| `<category term="..." scheme="..." />` 中 `scheme` 含 `primary` 的 | `primary_category` | 主分类 |

### 第 4 步：过滤相关论文

纳入规则 — 标题或摘要中包含以下关键词之一（不区分大小写）：

`llm`、`large language model`、`agent`、`rag`、`retrieval augmented`、`multimodal`、`多模态`、`fine-tun`、`微调`、`alignment`、`safety`、`对齐`、`安全`、`reasoning`、`推理`、`chain-of-thought`、`tool`、`function calling`、`embedding`、`向量`、`benchmark`、`evaluation`、`评测`、`prompt`、`in-context`、`transformer`、`attention`、`rlhf`、`dpo`、`distill`、`蒸馏`、`quantiz`、`量化`、`mixture of expert`、`moe`

排除规则：

- 标题或摘要中包含 `survey` 且 primary_category 为 `cs.AI` 或 `cs.LG` 的综述论文（综述由 tech-summary 单独处理）
- 标题以 `Correction:` 开头或包含 `Erratum` 的勘误/更正文

### 第 5 步：去重

与 `knowledge/raw/arxiv-papers-*.json` 文件中近 60 天已采集的条目进行比对：

- 按 `arxiv_id` 精确去重
- 若存在同标题（相似度 > 90%）但 `arxiv_id` 不同的情况，标记为「疑似重复」并记录日志，不纳入本次输出

### 第 6 步：撰写中文摘要并排序

为每个通过过滤和去重的论文生成中文摘要，使用公式：

> **论文名（英文原名保留）** + 提出/研究了什么（1 短句概括核心方法或发现） + 关键结论/亮点（1 句）

摘要长度限制在 60 字以内。

排序规则：

1. 按 `published` 降序（越新越靠前）
2. 同日论文按标题字母序

取前 20 条。若有效条目不足 20 条，输出实际数量。

### 第 7 步：输出 JSON

将最终结果写入 `knowledge/raw/arxiv-papers-YYYY-MM-DD.json`，其中 `YYYY-MM-DD` 为采集日期。

文件名示例：`knowledge/raw/arxiv-papers-2026-05-05.json`

## 注意事项

- **API 限流**：arXiv API 对连续请求有限流，单次请求间隔至少 5 秒，批次拉取时通过分页（`start=0 -> start=50`）避免瞬时压力
- **跨天处理**：采集时间为 UTC 每日 06:00，抓取范围覆盖前 3 天（避免因时区偏差遗漏论文）
- **首次作者上限**：作者列表截断至前 5 位，末尾追加 `et al.` 指示含更多作者
- **摘要质量**：中文摘要须基于理解翻译而非逐句直译，确保技术术语准确（如 `chain-of-thought` 译作「思维链」，`fine-tuning` 译作「微调」）
- **分类代码**：`primary_category` 从 `<category>` 标签中识别（`scheme` 属性含 `primary`），若缺失则取第一个 `<category>`

## 输出格式

```json
{
  "source": "arxiv",
  "skill": "arxiv-papers",
  "collected_at": "2026-05-05T06:00:00Z",
  "query": {
    "categories": ["cs.AI", "cs.CL", "cs.LG", "cs.MA", "cs.HC"],
    "date_range": "2026-05-02 to 2026-05-05",
    "max_results": 100
  },
  "total_matched": 23,
  "total_filtered": 20,
  "items": [
    {
      "arxiv_id": "2405.12345",
      "title": "Scaling Multi-Agent Reinforcement Learning with Graph Neural Networks",
      "url": "https://arxiv.org/abs/2405.12345",
      "summary": "Scaling Multi-Agent Reinforcement Learning：提出用图神经网络建模多智能体间动态拓扑关系，在大规模协作任务中收敛速度相比 MADDPG 提升 3 倍。",
      "authors": ["Alice Chen", "Bob Wang", "Charlie Li", "Diana Zhang", "Eve Liu et al."],
      "published": "2026-05-04T12:00:00Z",
      "updated": "2026-05-05T03:00:00Z",
      "primary_category": "cs.MA",
      "categories": ["cs.MA", "cs.AI", "cs.LG"]
    }
  ]
}
```

| 字段                        | 类型         | 说明                                      |
| --------------------------- | ------------ | ----------------------------------------- |
| `source`                    | `str`        | 固定值 `"arxiv"`                          |
| `skill`                     | `str`        | 固定值 `"arxiv-papers"`                   |
| `collected_at`              | `str` (ISO)  | 采集时间戳（UTC）                         |
| `query`                     | `dict`       | 本次查询参数记录                          |
| `query.categories`          | `list[str]`  | 查询的分类列表                            |
| `query.date_range`          | `str`        | 查询的时间范围                            |
| `query.max_results`         | `int`        | 请求的最大结果数                          |
| `total_matched`             | `int`        | API 返回的原始条目数（过滤前）            |
| `total_filtered`            | `int`        | 过滤与去重后的最终条目数                  |
| `items`                     | `list[dict]` | 论文列表                                  |
| `items[].arxiv_id`          | `str`        | arXiv 论文 ID                             |
| `items[].title`             | `str`        | 论文标题（英文原文）                      |
| `items[].url`               | `str`        | 论文 arXiv 页面 URL                       |
| `items[].summary`           | `str`        | 中文摘要（≤60 字）                        |
| `items[].authors`           | `list[str]`  | 作者列表（前 5 位 + et al.）              |
| `items[].published`         | `str` (ISO)  | 首次提交日期                              |
| `items[].updated`           | `str` (ISO)  | 最后更新日期                              |
| `items[].primary_category`  | `str`        | 主分类代码（如 `cs.AI`）                  |
| `items[].categories`        | `list[str]`  | 所有分类代码列表                          |
