# AI 知识库 · 三 Agent PRD v0.1

## 总流程

每天 UTC 0:00 触发，三个 Agent 串行执行：

```
collector → analyzer → organizer
```

## Agent 职责

### 采集 Agent (collector)

- 从 GitHub Trending 和 Hacker News 采集技术动态，共 20 条
- 过滤 AI 相关内容
- 输出到 `knowledge/raw/`

### 分析 Agent (analyzer)

- 读取 `knowledge/raw/` 中的原始数据
- 给每条打 3 维度标签：
  - **技术方向**：`llm` / `agent` / `rag` / `multimodal` / `code-gen` / `fine-tuning` / `inference` / `training` / `dataset` / `tool` / `framework` / `application`
  - **质量等级**：`S`(9-10 改变格局) / `A`(7-8 直接有帮助) / `B`(5-6 值得了解) / `C`(1-4 可略过)
  - **适用场景**：一句话描述谁会用、怎么用
- 生成摘要（中文 2-3 句话）
- 提取亮点（2-3 个核心亮点）

### 整理 Agent (organizer)

- 读取已标注的数据
- 去重检查（按 url 去重）
- 整理成标准 JSON 格式
- 存入 `knowledge/articles/`

## 输出 JSON 格式

### collector 输出 (knowledge/raw/)

```json
[
  {
    "title": "项目名称",
    "url": "https://github.com/...",
    "source": "github|hackernews",
    "popularity": 12345,
    "summary": "一句话中文摘要"
  }
]
```

### analyzer 输出 (knowledge/raw/)

```json
[
  {
    "title": "项目名称",
    "url": "https://github.com/...",
    "source": "github|hackernews",
    "popularity": 12345,
    "summary": "中文摘要（2-3 句话）",
    "highlights": ["亮点1", "亮点2"],
    "tech_direction": "llm|agent|rag|...",
    "quality_level": "S|A|B|C",
    "use_case": "适用场景描述"
  }
]
```

### organizer 输出 (knowledge/articles/)

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

## 开放问题

1. **上游失败下游怎么办？**
   - collector 失败 → 终止流程，记录错误
   - analyzer 失败 → 跳过该条，继续处理其他
   - organizer 失败 → 重试一次，仍失败则记录错误

2. **数据怎么传？**
   - 通过文件传递：`knowledge/raw/` → `knowledge/articles/`
   - 不使用消息队列，保持简单

3. **重跑策略？**
   - 手动触发 workflow
   - 支持指定日期重跑
   - 已存在的文件跳过，不覆盖

4. **进度追踪？**
   - 日志记录每个 Agent 的开始/结束时间
   - 记录成功/失败条数
   - 错误详情写入日志文件
