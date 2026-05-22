---
name: hackernews
description: 当需要采集 Hacker News 热门帖子时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# Hacker News 采集技能

## 使用场景

当需要获取 Hacker News 上当前热门的技术讨论时使用此技能，特别关注 AI/LLM/Agent 领域的内容。

## 执行步骤

### 1. 获取热门帖子 ID

调用 Hacker News API，获取当前热门帖子的 ID 列表：

```
GET https://hacker-news.firebaseio.com/v0/topstories.json
```

取前 100 个 ID。

### 2. 获取帖子详情

对每个 ID，调用 API 获取帖子详情：

```
GET https://hacker-news.firebaseio.com/v0/item/{id}.json
```

提取字段：
- `title`: 帖子标题
- `url`: 帖子链接
- `score`: 得分（points）
- `time`: 发布时间

### 3. 过滤

**纳入条件**（满足任一即可）：
- 标题中包含：`llm`, `ai`, `machine-learning`, `transformer`, `diffusion`, `neural`, `deep-learning`, `nlp`, `computer-vision`, `agent`, `rag`, `GPT`, `Claude`, `Gemini`, `Llama`

**排除条件**：
- 标题为空
- 链接为空（Ask HN 类型）

### 4. 去重

检查 `knowledge/raw/` 目录下已有的文件，按 `url` 字段去重，避免重复收录。

### 5. 撰写中文摘要

为每个帖子撰写一句话中文摘要，遵循公式：

```
{帖子标题} + 核心内容 + 为什么值得关注
```

示例：
```
这篇帖子讨论了 GPT-5 的可能架构，提出了多模态融合的新思路，对理解 LLM 发展方向有参考价值。
```

### 6. 排序取 Top 15

按得分（points）降序排序，取前 15 条数据。

### 7. 输出 JSON

将结果保存到 `knowledge/raw/hackernews-YYYY-MM-DD.json`。

## 注意事项

- Hacker News API 公开可用，无需认证
- API 调用失败时记录日志，跳过该条
- 网络超时重试 3 次，仍失败则跳过
- 摘要必须使用中文，简洁准确
- 不编造数据，所有信息来自实际抓取

## 输出格式

```json
{
  "source": "hackernews",
  "skill": "hackernews",
  "collected_at": "2026-05-21T08:00:00Z",
  "items": [
    {
      "name": "帖子标题",
      "url": "https://example.com",
      "summary": "一句话中文摘要",
      "stars": 100,
      "language": null,
      "topics": ["ai", "llm"]
    }
  ]
}
```
