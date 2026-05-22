---
name: deepseek-analyzer
description: 当需要使用 DeepSeek API 分析项目时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# DeepSeek 分析技能

## 使用场景

当需要对采集到的项目进行深度分析，生成摘要、亮点、标签时使用此技能。

## 执行步骤

### 1. 读取原始数据

从 `knowledge/raw/` 目录下读取需要分析的 JSON 文件。

### 2. 准备分析请求

为每个条目构建分析请求：
- 项目名称
- 项目链接
- 项目描述
- Stars 数量
- 话题标签

### 3. 调用 DeepSeek API

使用 OpenAI 兼容格式调用 DeepSeek API：

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.deepseek.com/v1",
    api_key="your_api_key"
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "你是一个 AI 技术分析专家"},
        {"role": "user", "content": prompt}
    ],
    temperature=0.3,
    response_format={"type": "json_object"}
)
```

### 4. 解析响应

从 API 响应中提取以下字段：
- `summary`: 中文摘要（2-3 句话）
- `highlights`: 核心亮点数组（2-3 个）
- `tech_direction`: 技术方向
- `quality_level`: 质量等级
- `use_case`: 适用场景

### 5. 验证结果

检查返回的 JSON 是否包含所有必填字段：
- `tech_direction`: 必须是预定义的技术方向之一
- `quality_level`: 必须是 S/A/B/C 之一
- `use_case`: 必须是非空字符串

### 6. 补充标签

根据分析结果，为条目添加标签：
- 技术方向标签（1 个）
- 相关技术标签（2-4 个）

### 7. 输出结果

将分析结果保存到 `knowledge/raw/` 目录下，覆盖原文件或创建新文件。

## 注意事项

- 需要配置 `DEEPSEEK_API_KEY` 环境变量
- API 调用失败时记录日志，返回默认值
- 评分要严格，不随意给高分
- 摘要必须使用中文，简洁准确
- 不编造数据，所有信息来自 API 分析

## 输出格式

```json
{
  "source": "deepseek-analyzer",
  "skill": "deepseek-analyzer",
  "analyzed_at": "2026-05-21T08:00:00Z",
  "items": [
    {
      "name": "项目名称",
      "url": "https://github.com/owner/repo",
      "summary": "中文摘要（2-3 句话）",
      "highlights": ["亮点1", "亮点2"],
      "tech_direction": "llm",
      "quality_level": "A",
      "use_case": "开发者可以用这个工具...",
      "tags": ["llm", "agent", "framework"]
    }
  ]
}
```

## 技术方向说明

| 方向 | 说明 |
|------|------|
| `llm` | 大语言模型 |
| `agent` | AI Agent |
| `rag` | 检索增强生成 |
| `multimodal` | 多模态 |
| `code-gen` | 代码生成 |
| `fine-tuning` | 微调 |
| `inference` | 推理 |
| `training` | 训练 |
| `dataset` | 数据集 |
| `tool` | 工具 |
| `framework` | 框架 |
| `application` | 应用 |

## 质量等级说明

| 等级 | 分数 | 说明 |
|------|------|------|
| `S` | 9-10 | 改变格局：可能重塑 AI 领域的重要项目 |
| `A` | 7-8 | 直接有帮助：对开发者有实际价值 |
| `B` | 5-6 | 值得了解：有亮点但非必需 |
| `C` | 1-4 | 可略过：价值有限或过于小众 |
