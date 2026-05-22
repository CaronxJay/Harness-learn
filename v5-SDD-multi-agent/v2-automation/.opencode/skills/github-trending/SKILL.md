---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# github-trending — GitHub 热门项目采集技能

## 使用场景

- 每日定时采集 GitHub 上 AI / LLM / Agent 领域的热门开源项目
- 监控特定技术领域的开源动向与社区热度
- 为知识库的后续分析与分发提供原始素材

## 执行步骤

### 第 1 步：搜索热门仓库

调用 GitHub REST API 获取当日 trending 数据：

```
GET https://api.github.com/search/repositories?q=created:>{YYYY-MM-DD}&sort=stars&order=desc&per_page=50
```

同时抓取 GitHub Trending 页面作为补充：
- 日榜：`https://github.com/trending?since=daily`
- 周榜：`https://github.com/trending?since=weekly`

**数据源优先级**：API 返回数据 > Trending 页面 HTML 解析

### 第 2 步：提取信息

对每个仓库提取以下字段：

| 字段 | 来源 |
|------|------|
| `name` | `full_name`（如 `mannaandpoem/OpenManus`） |
| `url` | `html_url` |
| `stars` | `stargazers_count` |
| `language` | `language` 字段 |
| `topics` | `topics` 数组 |
| `description` | `description` 字段 |
| `forks` | `forks_count` |
| `created_at` | `created_at` / `pushed_at` |

### 第 3 步：过滤

**纳入条件**（满足至少一项）：
- `topics` 中包含：`llm`、`agent`、`rag`、`langchain`、`ai`、`machine-learning`、`deep-learning`、`gpt`、`transformer`、`nlp`、`prompt-engineering`、`multimodal`、`embedding`、`vector-database`、`inference`
- `description` 中包含：`LLM`、`Agent`、`RAG`、`AI`、`GPT`、`Transformer`、`fine-tune`、`prompt`、`diffusion`、`chatbot`
- `name` 中包含：`llm`、`agent`、`gpt`、`rag`、`langchain`

**排除条件**（满足任意一项则丢弃）：
- 标题以 `awesome-` 开头（Awesome 列表，非项目本身）
- `name` 中包含 `-list`、`interview-`、`tutorial-`（汇总型仓库）
- `stars` < 10（低质量信号）
- `archived: true`（已归档仓库）
- 已明确标记为 `fork`（原始项目更有价值）

### 第 4 步：去重

- 读取 `knowledge/raw/` 下所有历史采集文件
- 按 `url` 精确匹配去重，已采集过的项目不重复收录
- 若同一天内对同一仓库重复抓取，保留 `stars` 更新的一条

### 第 5 步：撰写中文摘要

使用以下公式为每个合格项目撰写中文摘要：

```
摘要 = 项目名 + 做了什么 + 为什么值得关注
```

要求：
- ≤80 字，一句话说明白
- 基于 `description` + README 内容提炼，不编造
- 中文表达自然，避免机械翻译腔
- 示例：
  > **OpenManus**：开源通才 Agent 框架，支持多工具调用与自主任务执行，社区一周内获万星关注。

### 第 6 步：排序取 Top 15

- 按 `stars` 降序排列
- 取前 15 条作为当日采集结果
- 若合格条目不足 15 条，有多少收多少，**不凑数**

### 第 7 步：输出 JSON 文件

将结果写入 `knowledge/raw/github-trending-YYYY-MM-DD.json`。

---

## 注意事项

- API 请求需携带合法的 `User-Agent` 头（GitHub API 要求）
- 未认证的 API 请求频率限制为 60 次/小时，合理控制请求频率
- 若 API 调用失败，降级到 Trending 页面 HTML 解析
- `summary` 不得编造项目能力或性能数据
- 输出文件名中的日期为采集日期，非项目创建日期
- 采集完成后打印统计信息：`总搜索数 / 过滤后 / 去重后 / 最终入库`

---

## 输出格式

```json
{
  "source": "github_trending",
  "skill": "github-trending",
  "collected_at": "2026-05-06T09:00:00+08:00",
  "stats": {
    "total_found": 50,
    "after_filter": 22,
    "after_dedup": 20,
    "final_count": 15
  },
  "items": [
    {
      "name": "mannaandpoem/OpenManus",
      "url": "https://github.com/mannaandpoem/OpenManus",
      "summary": "开源通才 Agent 框架，支持多工具调用与自主任务执行，社区一周内获万星关注。",
      "stars": 12400,
      "language": "Python",
      "topics": ["agent", "llm", "ai", "open-source"]
    }
  ]
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | 是 | 固定值 `github_trending` |
| `skill` | string | 是 | 固定值 `github-trending` |
| `collected_at` | datetime | 是 | 采集时间，ISO 8601，UTC+8 |
| `stats.total_found` | int | 是 | API 返回的原始总数 |
| `stats.after_filter` | int | 是 | 关键词过滤后剩余数 |
| `stats.after_dedup` | int | 是 | 去重后剩余数 |
| `stats.final_count` | int | 是 | 最终入库数（Top 15 截断后） |
| `items[].name` | string | 是 | `owner/repo` 格式 |
| `items[].url` | string | 是 | GitHub 仓库链接 |
| `items[].summary` | string | 是 | 中文摘要，≤80 字 |
| `items[].stars` | int | 是 | Star 数量 |
| `items[].language` | string | 是 | 主编程语言 |
| `items[].topics` | string[] | 是 | 仓库标签 |
