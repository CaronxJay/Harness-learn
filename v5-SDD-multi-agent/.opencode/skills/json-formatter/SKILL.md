---
name: json-formatter
description: 当需要将数据格式化为标准 JSON 时使用此技能
allowed-tools: Read, Grep, Glob, Write, Edit
---

# JSON 格式化技能

## 使用场景

当需要将采集到的数据格式化为标准 JSON 格式时使用此技能。

## 执行步骤

### 1. 读取原始数据

从 `knowledge/raw/` 目录下读取需要格式化的 JSON 文件。

### 2. 提取必要字段

从原始数据中提取以下字段：
- `name`: 项目名称
- `url`: 项目链接
- `summary`: 项目摘要
- `source`: 数据来源
- `stars`: Stars 数量
- `language`: 编程语言
- `topics`: 话题标签

### 3. 生成 UUID

为每个条目生成唯一的 UUID 作为 `id` 字段。

### 4. 转换字段名

将原始字段名转换为标准字段名：
- `name` → `title`
- `url` → `source_url`
- `source` → `source_type`

### 5. 添加元数据

为每个条目添加元数据：
- `status`: 设置为 `"analyzed"`
- `collected_at`: 设置为当前时间

### 6. 验证格式

检查格式化后的 JSON 是否符合标准：
- 所有必填字段都有值
- 字段类型正确
- JSON 格式有效

### 7. 输出结果

将格式化后的 JSON 保存到 `knowledge/articles/` 目录下。

## 注意事项

- 字段名要符合标准
- 字段值要符合类型要求
- JSON 格式要有效
- 不丢失数据，所有信息都要保留

## 输出格式

```json
{
  "id": "uuid",
  "title": "条目标题",
  "source_url": "来源链接",
  "source_type": "github|hackernews",
  "summary": "AI 生成摘要",
  "tags": ["llm", "agent", "rag"],
  "tech_direction": "llm",
  "quality_level": "A",
  "use_case": "适用场景描述",
  "status": "analyzed",
  "collected_at": "2026-03-01T10:00:00Z"
}
```
