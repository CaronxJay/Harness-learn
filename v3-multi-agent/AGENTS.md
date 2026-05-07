# AGENTS.md — AI 知识库助手

## 1. 项目概述

AI 知识库助手是一个自动化技术情报采集与分析系统。每日自动从 GitHub Trending、Hacker News 等渠道抓取 AI / LLM / Agent 领域的最新动态，经由 AI 分析、摘要、打标后结构化存储为 JSON，并通过 Telegram、飞书等渠道进行多端分发，帮助开发者高效追踪 AI 领域前沿进展。

## 2. 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.12 |
| Agent 编排 | OpenCode + 国产大模型 |
| 工作流引擎 | LangGraph |
| 多渠道推送 | OpenClaw (Telegram / 飞书) |

## 3. 编码规范

- 严格遵循 **PEP 8**，使用 `black` 或 `ruff` 进行格式化
- 所有变量、函数、方法统一使用 **snake_case** 命名
- 类名使用 **PascalCase**
- Docstring 采用 **Google 风格**（`Args:` / `Returns:` / `Raises:`），所有公开函数必须有 docstring
- 类型注解覆盖率应达到 100%（使用 `mypy` 或 `pyright` 检查）
- **禁止** 在业务代码中使用裸 `print()`，统一使用 `logging` 模块（logger name 为模块路径）
- 配置文件使用 `.env` + `python-dotenv` 加载，严禁硬编码任何密钥或 Token

## 4. 项目结构

```
ai-knowledge-base/
├── .opencode/
│   ├── agents/            # Agent 定义文件（采集/分析/整理）
│   └── skills/            # 可复用 Skill 定义
├── knowledge/
│   ├── raw/               # 原始采集数据（每日快照）
│   └── articles/          # AI 分析后的结构化知识条目
├── src/
│   ├── collectors/        # 数据采集模块（GitHub Trending / Hacker News）
│   ├── analyzers/         # AI 分析模块（摘要/打标/评分）
│   ├── publishers/        # 分发模块（Telegram / 飞书）
│   ├── models/            # 数据模型定义（Pydantic / dataclass）
│   └── workflows/         # LangGraph 工作流定义
├── tests/
├── .env.example           # 环境变量模板
├── AGENTS.md              # 本文件
└── README.md
```

## 5. 知识条目 JSON 格式

所有分析结果统一为以下结构，存储在 `knowledge/articles/` 下：

```json
{
  "id": "2026-05-06-github-trending-001",
  "title": "OpenManus: An open-source generalist agent framework",
  "source": "github_trending",
  "source_url": "https://github.com/mannaandpoem/OpenManus",
  "language": "en",
  "summary": "一个开源的通才 Agent 框架，支持多工具调用、记忆管理与自主任务执行。",
  "summary_en": "An open-source generalist agent framework supporting multi-tool calling, memory management, and autonomous task execution.",
  "tags": ["agent-framework", "llm", "open-source", "python"],
  "category": "agent-framework",
  "relevance_score": 0.92,
  "status": "published",
  "created_at": "2026-05-06T10:30:00+08:00",
  "updated_at": "2026-05-06T12:00:00+08:00",
  "metadata": {
    "stars": 12400,
    "hn_points": null,
    "original_language": "zh"
  }
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 唯一标识，格式 `{date}-{source}-{序号}` |
| `title` | string | 是 | 中文标题 |
| `source` | enum | 是 | 来源：`github_trending` / `hacker_news` |
| `source_url` | url | 是 | 原始链接 |
| `language` | enum | 是 | 原文语言：`zh` / `en` |
| `summary` | string | 是 | 中文摘要（≤200 字） |
| `summary_en` | string | 否 | 英文摘要（原文为英文时必填） |
| `tags` | string[] | 是 | 标签列表，至少 1 个 |
| `category` | enum | 是 | 分类，见下方分类枚举 |
| `relevance_score` | float | 是 | 相关度评分 0.0-1.0 |
| `status` | enum | 是 | `draft` / `published` / `archived` |
| `created_at` | datetime | 是 | ISO 8601 格式，UTC+8 |
| `updated_at` | datetime | 是 | ISO 8601 格式 |
| `metadata` | object | 否 | 来源特定的元数据 |

**分类枚举（category）：**

| 值 | 说明 |
|----|------|
| `agent-framework` | Agent 框架与工具 |
| `llm` | 大语言模型 |
| `research` | 学术论文与研究成果 |
| `application` | AI 应用与产品 |
| `infrastructure` | 基础设施与部署 |
| `benchmark` | 评测与基准测试 |
| `security` | AI 安全与对齐 |
| `multimodal` | 多模态 AI |

## 6. Agent 角色概览

| 角色 | 名称 | 职责 | 触发条件 |
|------|------|------|----------|
| 采集 Agent | `collector` | 从 GitHub Trending / Hacker News 抓取 AI 领域内容，去重后写入 `knowledge/raw/` | 定时触发（每日） |
| 分析 Agent | `analyzer` | 对原始数据做 AI 摘要、打标、评分，产出结构化 JSON 写入 `knowledge/articles/` | 采集完成后自动触发 |
| 分发 Agent | `publisher` | 读取待发布的知识条目，格式化为推送消息，通过 OpenClaw 发送到 Telegram / 飞书 | 分析完成后自动触发 |

**协作流程：**

```
定时调度 → collector → knowledge/raw/
                ↓
           analyzer → knowledge/articles/
                ↓
           publisher → Telegram / 飞书
```

## 7. 红线（绝对禁止）

1. **禁止** 在代码或配置文件中硬编码任何 API Key、Token、密码或密钥（使用 `.env` + 环境变量）
2. **禁止** 在未经用户明确指示的情况下提交 `git commit` 或推送代码
3. **禁止** 使用裸 `print()` 输出业务日志（统一使用 `logging` 模块）
4. **禁止** 绕过 AI 分析直接将原始抓取内容推送给用户
5. **禁止** 采集或分发任何违反相关法律法规的内容
6. **禁止** 未经用户确认修改 `knowledge/` 下已有的历史数据（只增不改、误删需确认）
7. **禁止** 在 Agent 流程中引入未定义的外部依赖（新依赖需先更新 `pyproject.toml` / `requirements.txt`）
