---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# GitHub Trending 采集技能

## 使用场景

- 每日自动化采集 GitHub Trending 仓库，追踪 AI/LLM/Agent 领域最新开源项目
- 为知识库管线提供原始数据输入，支撑后续分析、去重、分发环节

## 执行步骤

### 第 1 步：搜索热门仓库

调用 GitHub API（`GET https://api.github.com/search/repositories`）搜索近 7 天内创建的仓库，按 stars 降序排列。查询参数：

- `q=created:>{7天前日期}`
- `sort=stars`
- `order=desc`
- `per_page=100`

**注意**：若 API 限流（403），回退至 `WebFetch` 抓取 `https://github.com/trending` 页面。

### 第 2 步：提取信息

从 API 响应或页面中提取每个仓库的以下字段：

- `full_name` — 仓库全名（owner/repo）
- `html_url` — 仓库链接
- `description` — 仓库描述
- `stargazers_count` — Star 数量
- `language` — 主要语言
- `topics` — 主题标签列表

### 第 3 步：过滤

纳入规则：

- 标题、描述或 topics 中包含以下关键词之一：`AI`、`LLM`、`Agent`、`GPT`、`Transformer`、`RAG`、`多模态`、`multimodal`、`大模型`、`深度学习`、`deep learning`、`NLP`、`机器学习`、`machine learning`、`推理`、`reasoning`、`fine-tune`、`微调`、`embedding`、`向量`、`vector`、`langchain`、`autogen`、`crewai`、`openai`、`anthropic`、`claude`、`llama`、`mistral`、`gemini`

排除规则：

- 标题或 topics 中包含 `awesome`（不区分大小写）的 Awesome 列表类仓库
- 标题或 topics 中包含 `interview`、`tutorial`、`course` 的教程类仓库
- `language` 为空或仅为文档类（如 Markdown、Roff）

### 第 4 步：去重

与 `knowledge/raw/` 目录下近 30 天已采集的条目进行比对：

- 按 `full_name` 精确去重（同名仓库不重复采集）
- 按 `html_url` 精确去重

### 第 5 步：撰写中文摘要

为每个通过过滤和去重的仓库生成中文摘要，使用公式：

> **项目名** + 做什么（一句话概括核心功能与目标） + 为什么值得关注（技术亮点 / 创新点 / 应用价值）

摘要长度限制在 80 字以内。

### 第 6 步：排序取 Top 15

按 `stargazers_count` 降序排列，取前 15 条。若有效条目不足 15 条，则输出实际数量。

### 第 7 步：输出 JSON

将最终结果写入 `knowledge/raw/github-trending-YYYY-MM-DD.json`，其中 `YYYY-MM-DD` 为采集日期。

## 注意事项

- API 访问频率控制在每分钟 10 次以内，避免触发 GitHub 限流
- 若 GitHub API 不可用，使用 `WebFetch` 抓取 Trending 页面作为备用数据源，但此时仅能获取 Top 25 且缺少 topics 字段
- 日期计算使用 UTC 时间，确保与知识库其他组件时间戳一致
- 摘要生成要求简洁、准确，避免空洞的赞誉词（如"革命性"、"颠覆性"）

## 输出格式

```json
{
  "source": "github",
  "skill": "github-trending",
  "collected_at": "2026-05-05T08:00:00Z",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "项目名：一句话概括核心功能与目标。技术亮点或应用价值简述。",
      "stars": 15000,
      "language": "Python",
      "topics": ["llm", "agent", "openai"]
    }
  ]
}
```

| 字段            | 类型         | 说明                     |
| --------------- | ------------ | ------------------------ |
| `source`        | `str`        | 固定值 `"github"`        |
| `skill`         | `str`        | 固定值 `"github-trending"` |
| `collected_at`  | `str` (ISO)  | 采集时间戳（UTC）        |
| `items`         | `list[dict]` | 热门仓库列表              |
| `items[].name`  | `str`        | 仓库全名（owner/repo）   |
| `items[].url`   | `str`        | 仓库链接                 |
| `items[].summary` | `str`      | 中文摘要（≤80 字）       |
| `items[].stars` | `int`        | Star 数量                |
| `items[].language` | `str`     | 主要编程语言             |
| `items[].topics` | `list[str]` | 主题标签列表             |
