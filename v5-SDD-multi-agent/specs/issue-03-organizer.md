# Issue #03 · Organizer Agent

## Depends on
- Issue #01 · Collector Agent（必须先产出 knowledge/raw/*.json）
- Issue #02 · Analyzer Agent（必须先产出带标签的 knowledge/raw/*.json）

## Description
读取已标注的 knowledge/raw/*.json，去重检查、格式化为标准 JSON、分类存入 knowledge/articles/。

## Acceptance Criteria
- [x] 读取 knowledge/raw/*.json 中已标注的数据
- [x] 去重检查（按 url 去重，避免重复收录）
- [x] 格式化为标准 JSON 格式（见 specs/schemas/article.json）
- [x] 生成 UUID 作为 id
- [x] 设置 status 为 "analyzed"
- [x] 存储到 knowledge/articles/{date}-{source}-{slug}.json
- [x] 失败处理：去重失败 → 记日志 + skip，不抛异常
- [x] 重跑：幂等（同一输入多次运行结果一致）

## 实现细节

### 文件结构
- `src/organizer.py`: 整理 Agent 主模块
- `specs/schemas/article.json`: Article JSON Schema 定义
- `tests/test_organizer.py`: 单元测试

### 核心功能
1. **load_analyzed_data**: 加载已标注的数据
   - 从 `knowledge/raw/` 读取文件
   - 解析 JSON 数组

2. **check_duplicate**: 去重检查
   - 读取 `knowledge/articles/` 中已有文件
   - 按 `url` 字段去重
   - 已存在的条目直接跳过

3. **format_article**: 格式化为标准 JSON
   - 确保字段完整：`id`, `title`, `source_url`, `source_type`, `summary`, `tags`, `tech_direction`, `quality_level`, `use_case`, `status`, `collected_at`
   - 生成 UUID 作为 `id`
   - 设置 `status` 为 `"analyzed"`

4. **save_article**: 保存文章
   - 存储路径：`knowledge/articles/{date}-{source}-{slug}.json`
   - 文件命名规范：
     - `{date}`: 采集日期，格式 `YYYY-MM-DD`
     - `{source}`: 来源，`github` 或 `hackernews`
     - `{slug}`: 项目名称的 slug 化（小写、连字符分隔）
   - 示例：`2026-05-21-github-langgraph.json`

### 输出格式
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

### 错误处理
- 文件不存在：记录日志，返回空数组
- JSON 解析错误：记录日志，返回空数组
- 去重失败：记录日志，跳过该条
- 保存失败：记录日志，跳过该条

### 测试覆盖
- [x] 测试加载已标注数据
- [x] 测试去重检查
- [x] 测试格式化文章
- [x] 测试保存文章
- [x] 测试错误处理

## 使用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 运行整理
python3 src/organizer.py

# 运行测试
python3 -m pytest tests/test_organizer.py -v
```
