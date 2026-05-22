---
name: dedup-checker
description: 当需要检查数据重复时使用此技能
allowed-tools: Read, Grep, Glob
---

# 去重检查技能

## 使用场景

当需要检查采集到的数据是否与已有数据重复时使用此技能。

## 执行步骤

### 1. 读取已有数据

从 `knowledge/articles/` 目录下读取所有 JSON 文件，提取 `source_url` 字段。

### 2. 构建 URL 索引

将所有已有的 `source_url` 构建为索引，便于快速查找。

### 3. 读取待检查数据

从 `knowledge/raw/` 目录下读取待检查的 JSON 文件。

### 4. 逐条检查

对待检查数据中的每一条，检查其 `url` 是否已存在于索引中。

### 5. 标记重复项

对重复的条目标记为 `duplicate: true`。

### 6. 统计结果

统计检查结果：
- 总条目数
- 重复条目数
- 新增条目数

### 7. 输出结果

将检查结果保存到新文件或返回给调用方。

## 注意事项

- 去重检查基于 `url` 字段
- URL 比较区分大小写
- 空 URL 视为不重复
- 检查失败时记录日志，跳过该条

## 输出格式

```json
{
  "total": 100,
  "duplicate": 20,
  "new": 80,
  "items": [
    {
      "url": "https://example.com",
      "duplicate": false
    }
  ]
}
```
