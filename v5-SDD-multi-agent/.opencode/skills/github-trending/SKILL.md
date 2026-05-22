---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# GitHub Trending 采集技能

## 使用场景

当需要获取 GitHub 上当前热门的开源项目时使用此技能，特别关注 AI/LLM/Agent 领域的项目。

## 执行步骤

### 1. 搜索热门仓库

调用 GitHub Search API，搜索最近 24 小时内 stars 增长最快的仓库：

```
GET https://api.github.com/search/repositories
Query: stars:>100 created:>{24h_ago}
Sort: stars
Order: desc
```

### 2. 提取信息

从 API 响应中提取以下字段：
- `full_name`: 仓库全名
- `html_url`: 仓库链接
- `stargazers_count`: stars 数量
- `language`: 主要编程语言
- `topics`: 话题标签数组
- `description`: 项目描述

### 3. 过滤

**纳入条件**（满足任一即可）：
- 话题标签包含：`llm`, `ai`, `machine-learning`, `transformer`, `diffusion`, `neural`, `deep-learning`, `nlp`, `computer-vision`, `agent`, `rag`
- 描述中包含上述关键词

**排除条件**：
- 仓库名包含 `awesome-`（Awesome 列表）
- 描述为空或过短（少于 10 个字符）

### 4. 去重

检查 `knowledge/raw/` 目录下已有的文件，按 `url` 字段去重，避免重复收录。

### 5. 撰写中文摘要

为每个项目撰写一句话中文摘要，遵循公式：

```
{项目名} + 做什么 + 为什么值得关注
```

示例：
```
LangGraph 是 LangChain 的图结构 Agent 框架，支持复杂工作流编排，适合需要多步决策的 AI 应用。
```

### 6. 排序取 Top 15

按 stars 数量降序排序，取前 15 条数据。

### 7. 输出 JSON

将结果保存到 `knowledge/raw/github-trending-YYYY-MM-DD.json`。

## 注意事项

- 需要配置 `GITHUB_TOKEN` 环境变量
- API 调用失败时记录日志，跳过该条
- 网络超时重试 3 次，仍失败则跳过
- 摘要必须使用中文，简洁准确
- 不编造数据，所有信息来自实际抓取

## 输出格式

```json
{
  "source": "github-trending",
  "skill": "github-trending",
  "collected_at": "2026-05-21T08:00:00Z",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "一句话中文摘要",
      "stars": 12345,
      "language": "Python",
      "topics": ["llm", "agent"]
    }
  ]
}
```
