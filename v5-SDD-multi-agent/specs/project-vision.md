# AI 知识库 · 项目愿景 v0.1

## 要做什么
- 自动采集 GitHub Trending、Hacker News 等渠道的 AI/LLM/Agent 技术动态
- 每天抓取 GitHub Trending Top 20 条
- 全量抓取，用关键词（`llm`, `ai`, `machine-learning`, `transformer`, `diffusion` 等）或 topic 标签筛选 AI 相关项目
- 用 Agent 分析每个项目，输出以下维度：
  - 项目定位（一句话描述）
  - 技术栈
  - 核心亮点（为什么上 Trending）
  - 适用场景
  - 关联趋势（Agent、RAG、多模态等）
- 输出 JSON 格式知识条目，支持多渠道分发（QQBot、飞书）

## 知识条目 JSON 格式

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
  "status": "raw|analyzed|published",
  "collected_at": "2026-03-01T10:00:00Z"
}
```

## 不做什么
- 不做实时抓取（只定时，不提供即时查询）
- 不做项目代码深度分析（只分析 README 和表面信息）
- 不做自动部署或运行示例项目
- 不做人工审核（全自动，容错靠 Agent）

## 边界 & 验收
- 每天定时任务自动运行，无需人工干预
- 输出 JSON 文件，每条包含上述所有字段
- 筛选准确率 > 80%（抽查 10 条，至少 8 条确实是 AI 相关）
- 分析质量可用（亮点、场景描述准确，非废话）

## 怎么验证
- 跑一周，检查输出文件
- 抽查 10 条人工评分
