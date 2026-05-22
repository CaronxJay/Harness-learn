# AGENTS.md — AI 知识库助手

## 1. 项目概述

AI 知识库助手是一个自动化技术情报采集与分析系统。每日从 GitHub Search API、arXiv RSS 等渠道抓取 AI / LLM / Agent 领域的最新动态，经由 LLM 分析、摘要、打标后结构化存储为 JSON，帮助开发者高效追踪 AI 领域前沿进展。

Pipeline 分四步执行：采集 → 分析 → 整理 → 保存，支持通过 `--step` 参数分阶段运行。

## 2. 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.12 |
| Agent 编排 | OpenCode + 国产大模型 |
| 工作流引擎 | LangGraph |
| 多渠道推送 | OpenClaw (Telegram / 飞书) |

## 3. 编码规范

- 严格遵循 **PEP 8**
- 所有变量、函数、方法统一使用 **snake_case** 命名
- 类名使用 **PascalCase**
- Docstring 采用 **Google 风格**（`Args:` / `Returns:` / `Raises:`），所有公开函数必须有 docstring
- 类型注解覆盖率应达到 100%
- **禁止** 在业务代码中使用裸 `print()`，统一使用 `logging` 模块（logger name 为模块路径）
- 配置文件使用 `.env` + 环境变量，**严禁** 硬编码任何密钥或 Token

## 4. 项目结构

```
v2-automation/
├── .opencode/
│   ├── agents/                # Agent 定义（collector / analyzer / organizer）
│   ├── skills/                # Skill 定义（github-trending / arxiv-papers / tech-summary）
│   └── plugins/               # OpenCode 插件
├── hooks/
│   ├── check_quality.py       # 数据质量检查
│   └── validate_json.py       # JSON 格式校验
├── knowledge/
│   ├── raw/                   # 原始采集数据（每日快照，JSON）
│   └── articles/              # AI 分析后的结构化知识条目（JSON）
├── logs/
│   ├── collect.log            # 采集日志（crontab 输出）
│   └── analyze.log            # 分析日志（crontab 输出）
├── pipeline/
│   ├── pipeline.py            # 主流水线（采集 → 分析 → 整理 → 保存）
│   ├── model_client.py        # LLM 客户端（DeepSeek / Qwen / OpenAI） + CostTracker
│   ├── mcp_knowledge_server.py # MCP 知识库服务
│   └── rss_sources.yaml       # RSS 采集源配置
├── .env                       # 环境变量（API Key 等，不入库）
├── crontab.conf               # crontab 定时任务配置
├── opencode.json              # OpenCode 配置文件
├── requirements.txt           # Python 依赖
└── AGENTS.md                  # 本文件
```

## 5. Pipeline 命令

### 完整运行

```bash
python3 pipeline/pipeline.py --limit 20
```

### 分阶段运行

```bash
# 阶段一：采集 + 分析（免费模型，适合每日定时）
python3 pipeline/pipeline.py --step 1 --step 2 >> logs/collect.log 2>&1

# 阶段二：整理 + 保存（需 API Key，适合每周定时）
python3 pipeline/pipeline.py --step 3 --step 4 >> logs/analyze.log 2>&1
```

中间结果保存在 `knowledge/.pipeline_intermediate.json`，阶段二完成后自动清理。

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--step {1,2,3,4}` | int | 全部 | 指定执行步骤，可多次使用 |
| `--sources` | str | `github,rss` | 采集源，逗号分隔（github / rss） |
| `--limit` | int | 20 | 采集条目数上限 |
| `--dry-run` | flag | false | 干跑模式，不写入文件 |
| `--verbose` | flag | false | 输出详细日志 |

### 日志

```bash
cat logs/collect.log   # 查看采集日志
cat logs/analyze.log   # 查看分析日志
```

## 6. 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_PROVIDER` | 否 | LLM 提供商（deepseek / qwen / openai），默认 deepseek |
| `{PROVIDER}_API_KEY` | 是 | 对应提供商的 API Key（如 `DEEPSEEK_API_KEY`） |
| `API_KEY` | 否 | 通用 API Key（当 `{PROVIDER}_API_KEY` 未设置时使用） |
| `GITHUB_TOKEN` | 否 | GitHub API Token（提升速率限制） |

## 7. LLM 提供商

| Provider | 默认模型 | 输入价格（元/百万 tokens） | 输出价格（元/百万 tokens） |
|----------|----------|-------------------------|--------------------------|
| deepseek | deepseek-chat | 1 | 2 |
| qwen | qwen-plus | 4 | 12 |
| openai | gpt-4o | 150 | 600 |

## 8. CostTracker

`model_client.py` 内置 `CostTracker` 类，每次 LLM API 调用成功后自动记录 token 消耗。Pipeline 运行结束时会打印成本报告：

```
==================================================
  LLM API 成本报告 (CNY)
==================================================
  [deepseek]
    调用次数 : 2
    输入     : 1,165 tokens
    输出     : 299 tokens
    估算成本 : ¥0.001763
==================================================
```

使用方式：

```python
from pipeline.model_client import cost_tracker

cost_tracker.estimated_cost("deepseek")  # 查看累计成本
cost_tracker.report()                    # 打印完整报告
```

## 9. Crontab 定时任务

```crontab
# 每天早上 08:00 运行 Step 1-2（免费采集）
0 8 * * * cd ~/v2-automation && python3 pipeline/pipeline.py --step 1 --step 2 >> logs/collect.log 2>&1

# 每周日上午 10:00 运行 Step 3-4（AI 分析入库）
0 10 * * 0 cd ~/v2-automation && python3 pipeline/pipeline.py --step 3 --step 4 >> logs/analyze.log 2>&1
```

安装：`crontab crontab.conf`

## 10. 知识条目 JSON 格式

所有分析结果统一为以下结构，存储在 `knowledge/articles/` 下：

```json
{
  "id": "2026-05-06-github-001",
  "title": "Agentic AI Roadmap",
  "source": "github_trending",
  "source_url": "https://github.com/romanyn36/agentic-ai-roadmap",
  "language": "en",
  "summary": "一个 AI Agent 学习路线图...",
  "summary_en": "A learning roadmap for AI agents...",
  "tags": ["agent-framework", "llm", "open-source"],
  "category": "agent-framework",
  "relevance_score": 0.90,
  "status": "published",
  "created_at": "2026-05-06T14:21:00+08:00",
  "updated_at": "2026-05-06T14:21:00+08:00",
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
| `source` | enum | 是 | 来源：`github_trending` / `hacker_news` / `arxiv` |
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

## 11. 红线（绝对禁止）

1. **禁止** 在代码或配置文件中硬编码任何 API Key、Token、密码或密钥（使用 `.env` + 环境变量）
2. **禁止** 在未经用户明确指示的情况下提交 `git commit` 或推送代码
3. **禁止** 使用裸 `print()` 输出业务日志（统一使用 `logging` 模块）
4. **禁止** 绕过 AI 分析直接将原始抓取内容推送给用户
5. **禁止** 采集或分发任何违反相关法律法规的内容
6. **禁止** 未经用户确认修改 `knowledge/` 下已有的历史数据（只增不改、误删需确认）
7. **禁止** 在 Agent 流程中引入未定义的外部依赖（新依赖需先更新 `requirements.txt`）
