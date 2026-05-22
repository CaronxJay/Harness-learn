---
name: ai-filter
description: 当需要过滤 AI/LLM/Agent 相关内容时使用此技能
allowed-tools: Read, Grep, Glob
---

# AI 内容过滤技能

## 使用场景

当需要从采集到的数据中筛选出 AI/LLM/Agent 相关内容时使用此技能。

## 执行步骤

### 1. 读取原始数据

从 `knowledge/raw/` 目录下读取需要过滤的 JSON 文件。

### 2. 提取关键词

从每个条目中提取以下字段用于匹配：
- `name`: 项目名称
- `summary`: 项目摘要
- `topics`: 话题标签数组

### 3. 关键词匹配

**AI 相关关键词列表**：
- `llm`
- `ai`
- `machine-learning`
- `transformer`
- `diffusion`
- `neural`
- `deep-learning`
- `nlp`
- `computer-vision`
- `agent`
- `rag`
- `GPT`
- `Claude`
- `Gemini`
- `Llama`

**匹配规则**：
- 不区分大小写
- 支持部分匹配（如 `llm` 匹配 `llama`）
- 标题、摘要、话题标签中任一命中即保留

### 4. 排除噪音

**排除条件**：
- Awesome 列表（名称包含 `awesome-`）
- 描述过短（少于 10 个字符）
- 非技术内容（如招聘、活动等）

### 5. 标记分类

为每个条目添加 `ai_relevance` 字段：
- `high`: 标题或摘要中直接包含 AI 关键词
- `medium`: 话题标签中包含 AI 关键词
- `low`: 仅描述中提及

### 6. 统计结果

统计过滤结果：
- 总条目数
- 保留条目数
- 过滤条目数
- 各分类条目数

### 7. 输出结果

将过滤后的数据保存到新文件或覆盖原文件。

## 注意事项

- 关键词列表可在配置文件中修改
- 匹配失败的条目直接跳过
- 保留原始数据，过滤结果另存为新文件
- 过滤规则应定期更新以适应新的 AI 术语

## 输出格式

```json
{
  "source": "ai-filter",
  "skill": "ai-filter",
  "filtered_at": "2026-05-21T08:00:00Z",
  "stats": {
    "total": 100,
    "kept": 25,
    "filtered": 75,
    "high": 10,
    "medium": 10,
    "low": 5
  },
  "items": [
    {
      "name": "项目名称",
      "url": "https://example.com",
      "summary": "项目摘要",
      "ai_relevance": "high"
    }
  ]
}
```
