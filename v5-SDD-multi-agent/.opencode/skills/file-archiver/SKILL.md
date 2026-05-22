---
name: file-archiver
description: 当需要将分析结果存档时使用此技能
allowed-tools: Read, Grep, Glob, Write, Edit
---

# 文件存档技能

## 使用场景

当需要将分析结果保存到指定目录时使用此技能。

## 执行步骤

### 1. 读取分析结果

从内存或文件中读取需要存档的分析结果。

### 2. 生成文件名

根据数据内容生成文件名，遵循规范：
- 格式：`{date}-{source}-{slug}.json`
- `{date}`: 采集日期，格式 `YYYY-MM-DD`
- `{source}`: 来源，`github` 或 `hackernews`
- `{slug}`: 项目名称的 slug 化（小写、连字符分隔）

示例：`2026-05-21-github-langgraph.json`

### 3. 检查目录

确保存储目录 `knowledge/articles/` 存在，如果不存在则创建。

### 4. 检查文件

检查目标文件是否已存在，避免覆盖。

### 5. 写入文件

将分析结果写入文件，确保：
- JSON 格式正确
- 编码为 UTF-8
- 缩进为 2 个空格

### 6. 验证文件

写入后验证文件：
- 文件是否存在
- 文件内容是否正确
- JSON 格式是否有效

### 7. 记录日志

记录存档结果：
- 成功：记录文件路径
- 失败：记录错误信息

## 注意事项

- 文件名要符合规范
- 不覆盖已有文件
- 写入失败时记录日志
- 确保 JSON 格式有效

## 输出格式

```json
{
  "success": true,
  "file_path": "knowledge/articles/2026-05-21-github-langgraph.json"
}
```
