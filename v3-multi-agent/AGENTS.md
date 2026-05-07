# AGENTS.md — AI 知识库助手

## 1. 项目概述

AI 知识库助手是一个自动化技术情报采集与分析系统。每日自动从 GitHub Search API、arXiv RSS 等渠道抓取 AI / LLM / Agent 领域的最新动态，经由 AI 分析、摘要、打标后结构化存储为 JSON，并通过 LangGraph 工作流编排实现从采集到入库的全链路自动化，帮助开发者高效追踪 AI 领域前沿进展。

## 2. 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.12 |
| Agent 编排 | OpenCode + 国产大模型 |
| 工作流引擎 | LangGraph (StateGraph + 8 节点流水线) |
| LLM 客户端封装 | pipeline/model_client.py（含重试、JSON 提取、CostGuard 预算熔断） |
| 质量保证 | 5 维度 LLM 审核 + hooks JSON 校验 + 5 维度质量评分 + human_flag 人工兜底 |
| 成本控制 | CostGuard 预算熔断 + token 用量追踪 + 每小时节点级成本报告 |

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
│   ├── agents/            # Agent 定义文件（collector / analyzer / organizer）
│   ├── skills/            # 可复用 Skill 定义（github-trending / arxiv-papers / tech-summary）
│   └── plugins/           # OpenCode 插件
├── .github/
│   └── workflows/         # GitHub Actions CI 配置
├── knowledge/
│   ├── raw/               # 原始采集数据（每日快照）
│   ├── articles/          # 结构化知识条目（含 index.json）
│   ├── pending_review/    # 人工介入待审核条目（HumanFlag 落盘）
│   ├── audit/             # 审核审计记录
│   └── reports/           # CostGuard 成本报告
├── workflows/             # LangGraph 工作流（8 节点 + 状态管理）
│   ├── graph.py           # StateGraph 组装与条件路由
│   ├── state.py           # KBState TypedDict 定义
│   ├── planner.py         # plan 节点：3 档采集策略（lite/standard/full）
│   ├── nodes.py           # collect / analyze / organize / save 节点实现
│   ├── reviewer.py        # review 节点：5 维度加权评分审核
│   ├── reviser.py         # revise 节点：根据审核反馈批量修正
│   ├── human_flag.py      # human_flag 节点：审核超限落盘 pending_review
│   └── model_client.py    # LLM 调用封装（chat / chat_json / CostGuard 集成）
├── pipeline/              # 独立流水线（CLI 可运行）
│   ├── pipeline.py        # 4 步主流程：采集 → 分析 → 整理 → 保存
│   ├── model_client.py    # LLM 客户端底层封装（create_provider / chat_with_retry）
│   └── mcp_knowledge_server.py  # MCP Knowledge Server（供外部 Agent 查询）
├── patterns/              # 可复用 Agent 设计模式
│   ├── supervisor.py      # Supervisor 监督模式（Worker → Reviewer → Retry）
│   └── router.py          # Router 路由模式
├── hooks/                 # 质量保证工具
│   ├── validate_json.py   # JSON 格式校验（必填字段、类型、ID、URL）
│   └── check_quality.py   # 5 维度质量评分（摘要/深度/格式/标签/空洞词）
├── tests/
│   ├── conftest.py        # 测试配置
│   ├── cost_guard.py      # CostGuard 预算熔断器
│   ├── security.py        # 输入清洗 / 输出过滤（注入防护 + PII 掩码）
│   ├── eval_test.py       # 评估测试
│   └── verify_injection.py  # 注入检测验证
├── opencode.json          # OpenCode 配置（MCP Server 注册）
├── requirements.txt       # 依赖声明
├── .env                   # 环境变量（API Key / 预算配置）
├── .gitignore
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
| `status` | enum | 是 | `draft` / `review` / `published` / `archived` |
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
| 整理 Agent | `organizer` | 去重校验、格式化为标准 JSON、分类存储、生成日汇总，写入 `knowledge/articles/` | 审核通过后自动触发 |

**LangGraph 工作流节点图：**

```
plan → collect → analyze → review ──passed──→ organize → save → END
                                   │    │
                                   │    └─ not passed, iter<3 ──→ revise → review (循环)
                                   │
                                   └─ not passed, iter>=3 → human_flag → END
```

**工作流节点说明：**

| 节点 | 文件 | 职责 |
|------|------|------|
| `plan` | workflows/planner.py | 3 档采集策略（lite/standard/full），控制每源抓取量、相关度阈值、最大审核轮数 |
| `collect` | workflows/nodes.py | 调用 GitHub Search API 采集 AI 相关仓库，注入清洗 |
| `analyze` | workflows/nodes.py | LLM 生成中文摘要、标签、评分（relevance_score 0.0-1.0） |
| `review` | workflows/reviewer.py | 5 维度加权评分审核（摘要/深度/相关性/原创性/格式），阈值 7.0，代码重算加权分 |
| `revise` | workflows/reviser.py | 根据审核反馈批量修正 analyses，保持字段完整性 |
| `organize` | workflows/nodes.py | 过滤低分、URL 去重、审核反馈修正、PII 掩码、格式标准化 |
| `save` | workflows/nodes.py | articles 落盘 JSON + 更新 index.json |
| `human_flag` | workflows/human_flag.py | 审核超限兜底，写入 `knowledge/pending_review/` |

## 7. 红线（绝对禁止）

1. **禁止** 在代码或配置文件中硬编码任何 API Key、Token、密码或密钥（使用 `.env` + 环境变量）
2. **禁止** 在未经用户明确指示的情况下提交 `git commit` 或推送代码
3. **禁止** 使用裸 `print()` 输出业务日志（统一使用 `logging` 模块）
4. **禁止** 绕过 AI 分析直接将原始抓取内容推送给用户
5. **禁止** 采集或分发任何违反相关法律法规的内容
6. **禁止** 未经用户确认修改 `knowledge/` 下已有的历史数据（只增不改、误删需确认）
7. **禁止** 在 Agent 流程中引入未定义的外部依赖（新依赖需先更新 `requirements.txt`）
