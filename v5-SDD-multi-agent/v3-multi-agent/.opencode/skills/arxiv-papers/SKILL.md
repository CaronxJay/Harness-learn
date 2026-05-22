---
name: arxiv-papers
description: 当需要采集 arXiv 最新 AI/LLM/Agent 领域学术论文时使用此技能
allowed-tools: Read, Grep, Glob, WebFetch
---

# arxiv-papers — arXiv 论文采集技能

## 使用场景

- 每日定时采集 arXiv 上 AI / LLM / Agent 领域最新提交的学术论文
- 追踪学术界前沿研究方向与技术突破
- 为知识库提供论文维度的原始素材，与工程类信息互补

## 执行步骤

### 第 1 步：搜索最新论文

调用 arXiv API 获取近期提交的 AI 相关论文：

```
GET http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG+OR+cat:cs.MA&sortBy=submittedDate&sortOrder=descending&max_results=50
```

**目标分类（categories）：**

| 分类 | 说明 |
|------|------|
| `cs.AI` | 人工智能 |
| `cs.CL` | 计算语言学 / NLP |
| `cs.LG` | 机器学习 |
| `cs.MA` | 多智能体系统 |
| `cs.CV` | 计算机视觉（仅限多模态/生成式） |
| `cs.IR` | 信息检索（仅限 RAG / 向量检索） |

**API 参数说明：**
- `sortBy=submittedDate` + `sortOrder=descending`：按提交日期降序，获取最新论文
- `max_results=50`：单次最多返回 50 条（arXiv API 限制）
- 响应格式为 Atom XML，需解析提取字段

### 第 2 步：提取信息

解析 Atom XML 响应，对每篇论文提取以下字段：

| 字段 | 来源 | 说明 |
|------|------|------|
| `arxiv_id` | `<id>` 标签 | 如 `arXiv:2505.01234v1`，去掉 `http://arxiv.org/abs/` 前缀 |
| `title` | `<title>` 标签 | 去除多余换行与空格 |
| `authors` | `<author>/<name>` 标签 | 作者列表，取前 5 名 + `et al.` |
| `abstract` | `<summary>` 标签 | 论文摘要原文，保留完整内容 |
| `pdf_url` | `<id>` 标签 | 替换 `abs` 为 `pdf` 得到 PDF 链接 |
| `categories` | `<category>` 标签 | arXiv 分类列表 |
| `published_date` | `<published>` 标签 | 首次提交日期 |
| `updated_date` | `<updated>` 标签 | 最近更新日期 |
| `comment` | `<arxiv:comment>` 标签 | 如 `Accepted at ICML 2026` |

### 第 3 步：过滤

**纳入条件**（满足至少一项）：

标题或摘要中包含以下关键词（大小写不敏感）：

| 类别 | 关键词 |
|------|--------|
| Agent 相关 | `agent`, `multi-agent`, `tool-use`, `tool-calling`, `function-calling`, `autonomous`, `planning`, `reasoning` |
| LLM 相关 | `llm`, `large-language-model`, `gpt`, `language-model`, `instruction-tuning`, `alignment`, `rlhf`, `prompt` |
| RAG 相关 | `rag`, `retrieval-augmented`, `retriever`, `knowledge-grounded`, `vector-search` |
| 训练/微调 | `fine-tune`, `fine-tuning`, `lora`, `qlora`, `peft`, `instruction-following`, `pre-training` |
| 推理/部署 | `inference`, `quantization`, `distillation`, `speculative-decoding`, `mixture-of-experts` |
| 多模态 | `multimodal`, `vision-language`, `text-to-image`, `text-to-video`, `diffusion`, `image-generation` |
| 评估 | `benchmark`, `evaluation`, `eval`, `leaderboard` |
| 安全 | `safety`, `alignment`, `jailbreak`, `red-teaming`, `hallucination` |

**排除条件**（满足任意一项则丢弃）：
- `comment` 中包含 `Withdrawn`（已撤回论文）
- 标题以 `Erratum:` / `Corrigendum:` / `Reply to:` / `Comment on:` 开头
- 纯数学/物理/生物等非 CS 分类论文
- 仅涉及传统 ML 方法（SVM、决策树、随机森林等）且不涉及 LLM/Agent
- 标题长度 < 15 字符（通常为摘要不完整或占位论文）

### 第 4 步：去重

- 读取 `knowledge/raw/` 下所有历史 `arxiv-papers-*.json` 文件
- 按 `arxiv_id` 精确匹配去重，同一论文不重复收录
- 若同一论文有版本更新（`v1` → `v2`），保留最新版本并标注 `updated_from: v1`

### 第 5 步：撰写中文摘要

使用以下公式为每篇合格论文撰写中文摘要：

```
摘要 = 论文要解决什么问题 + 提出的方法/核心思路 + 取得的关键结果
```

要求：
- ≤100 字（论文摘要通常比项目描述更复杂）
- 基于 `abstract` 内容提炼，忠实于原文
- 中文表达自然，避免机械翻译腔
- 不确定的结论需标注「（论文宣称）」
- 示例：
  > 提出 Multi-Agent 协作框架 AgentVerse，通过角色分配与任务分解实现多 Agent 高效协作。在 MMLU 和 HumanEval 上分别提升 **12%** 和 **8%**（论文宣称）。

### 第 6 步：排序取 Top 15

排序优先级（从高到低）：

1. **顶会论文**：`comment` 中包含 `Accepted at` / `Published at` 的论文优先
2. **首次提交**：`v1` 论文优先于更新版本
3. **提交日期**：最新提交的优先

取前 15 条作为当日采集结果。若合格条目不足 15 条，有多少收多少，**不凑数**。

### 第 7 步：输出 JSON 文件

将结果写入 `knowledge/raw/arxiv-papers-YYYY-MM-DD.json`。

---

## 注意事项

- arXiv API 请求频率限制较宽松，但每次请求之间建议间隔 ≥ 3 秒
- API 响应为 Atom XML 格式，需解析 `<entry>` 节点
- `title` 和 `abstract` 中可能包含 LaTeX 命令，提取时需做基本清理（如 `$\\alpha$` → `α`）
- 论文摘要（`abstract`）字段保留原文（英文），不做翻译
- 输出文件名中的日期为采集日期，非论文提交日期
- 采集完成后打印统计信息：`总搜索数 / 分类过滤后 / 关键词过滤后 / 去重后 / 最终入库`
- 若某篇论文同时属于多个分类，`categories` 保留完整列表

---

## 输出格式

```json
{
  "source": "arxiv_papers",
  "skill": "arxiv-papers",
  "collected_at": "2026-05-06T09:00:00+08:00",
  "stats": {
    "total_found": 50,
    "after_category_filter": 38,
    "after_keyword_filter": 22,
    "after_dedup": 20,
    "final_count": 15
  },
  "items": [
    {
      "arxiv_id": "2505.01234",
      "title": "AgentVerse: A Multi-Agent Collaboration Framework for Complex Task Solving",
      "authors": ["Wei Liu", "Ming Yang", "et al."],
      "abstract": "We propose AgentVerse, a multi-agent collaboration framework that enables LLM-based agents to cooperate on complex tasks through role assignment and task decomposition...",
      "pdf_url": "https://arxiv.org/pdf/2505.01234",
      "categories": ["cs.AI", "cs.MA", "cs.CL"],
      "summary": "提出 Multi-Agent 协作框架 AgentVerse，通过角色分配与任务分解实现多 Agent 高效协作。在 MMLU 和 HumanEval 上分别提升 12% 和 8%（论文宣称）。",
      "published_date": "2026-05-05",
      "comment": "Accepted at ICML 2026"
    }
  ]
}
```

**顶层字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | string | 是 | 固定值 `arxiv_papers` |
| `skill` | string | 是 | 固定值 `arxiv-papers` |
| `collected_at` | datetime | 是 | 采集时间，ISO 8601，UTC+8 |
| `stats.total_found` | int | 是 | API 返回的原始论文数 |
| `stats.after_category_filter` | int | 是 | 分类过滤后剩余数 |
| `stats.after_keyword_filter` | int | 是 | 关键词过滤后剩余数 |
| `stats.after_dedup` | int | 是 | 去重后剩余数 |
| `stats.final_count` | int | 是 | 最终入库数（Top 15 截断后） |
| `items` | array | 是 | 论文条目列表 |

**items 字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `arxiv_id` | string | 是 | arXiv 论文 ID，如 `2505.01234` |
| `title` | string | 是 | 论文标题（原文） |
| `authors` | string[] | 是 | 作者列表，取前 5 名 + `et al.` |
| `abstract` | string | 是 | 论文摘要原文（不翻译） |
| `pdf_url` | string | 是 | PDF 下载链接 |
| `categories` | string[] | 是 | arXiv 分类列表 |
| `summary` | string | 是 | 中文摘要，≤100 字 |
| `published_date` | string | 是 | 首次提交日期，YYYY-MM-DD |
| `comment` | string | 否 | 附带注释（如顶会接收信息） |
