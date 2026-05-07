# AGENTS.md — AI 知识库助手

## 1. 项目概述

AI 知识库助手是一个自动化技术情报采集、分析、分发与交互系统。每日自动从 GitHub Search API、arXiv RSS 等渠道抓取 AI / LLM / Agent 领域的最新动态，经由 AI 分析、摘要、打标后结构化存储为 JSON，通过 LangGraph 工作流编排实现从采集到入库的全链路自动化，并支持多渠道日报推送与终端用户交互查询，帮助开发者高效追踪 AI 领域前沿进展。

## 2. 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.12 |
| Agent 编排 | OpenCode + 国产大模型 |
| 工作流引擎 | LangGraph (StateGraph + 8 节点流水线) |
| LLM 客户端封装 | pipeline/model_client.py（含重试、JSON 提取、CostGuard 预算熔断） |
| 质量保证 | 5 维度 LLM 审核 + hooks JSON 校验 + 5 维度质量评分 + human_flag 人工兜底 |
| 成本控制 | CostGuard 预算熔断 + token 用量追踪 + 每小时节点级成本报告 |
| 消息推送 | QQ Bot (v2 API) / 飞书 Webhook / Telegram Bot / 企业微信 API |
| 交互查询 | KnowledgeBot 规则意图识别 + KnowledgeSearchEngine 关键词标签日期检索 |

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
├── bot/                   # 知识库交互模块
│   └── knowledge_bot.py   # KnowledgeBot 主入口 + SearchEngine / SubscriptionManager / PermissionManager
├── distribution/          # 多渠道日报推送模块
│   ├── formatter.py       # 多格式转换器（Markdown / Telegram / 飞书 / QQ / 微信）
│   └── publisher.py       # 推送器抽象基类 + TelegramPublisher / FeishuPublisher / QQPublisher / WeChatPublisher
├── knowledge/
│   ├── raw/               # 原始采集数据（每日快照）
│   ├── articles/          # 结构化知识条目（含 index.json）
│   ├── pending_review/    # 人工介入待审核条目（HumanFlag 落盘）
│   ├── audit/             # 审核审计记录
│   ├── reports/           # CostGuard 成本报告
│   ├── subscriptions.json # 用户订阅数据
│   └── permissions.json   # 用户权限数据
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
├── .env                   # 环境变量（API Key / 推送凭据 / 预算配置）
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

## 7. 多渠道日报推送

### 7.1 架构

`distribution/` 模块提供 OOP 架构的多渠道异步推送能力，统一入口 `publish_daily_digest()` 并发发布日报到所有已配置渠道。

```
publish_daily_digest(date_str, top_n, knowledge_dir)
  ├── TelegramPublisher   → generate_daily_digest() → json_to_telegram()   → API
  ├── FeishuPublisher     → generate_daily_digest() → json_to_feishu()     → Webhook
  ├── QQPublisher         → generate_daily_digest() → json_to_qq()         → API
  └── WeChatPublisher     → generate_daily_digest() → json_to_wechat()     → API
```

### 7.2 文件说明

| 文件 | 职责 |
|------|------|
| `distribution/formatter.py` | 6 种格式转换器（`json_to_markdown` / `json_to_telegram` / `json_to_feishu` / `json_to_qq` / `json_to_wechat`）+ `generate_daily_digest()` 日报聚合 |
| `distribution/publisher.py` | `BasePublisher` 抽象基类 + 4 个渠道推送器 + `publish_daily_digest()` 统一入口 |

### 7.3 推送渠道

| 渠道 | 类 | 环境变量 | 格式 |
|------|-----|----------|------|
| Telegram | `TelegramPublisher` | `TELEGRAM_BOT_TOKEN` `TELEGRAM_CHAT_ID` | MarkdownV2 |
| 飞书 | `FeishuPublisher` | `FEISHU_WEBHOOK_URL` | 交互式卡片 |
| QQ Bot | `QQPublisher` | `AppID` `AppSecret` `QQ_TARGET_ID` | Markdown (msg_type=2) |
| 企业微信 | `WeChatPublisher` | `WECOM_CORP_ID` `WECOM_CORP_SECRET` `WECOM_AGENT_ID` `chat_id` | Markdown |

### 7.4 消息格式

`generate_daily_digest(knowledge_dir, date_str, top_n)` 返回包含 5 种格式的聚合日报：

| 键 | 类型 | 说明 |
|----|------|------|
| `markdown` | str | 标准 Markdown（含头部汇总 + 分隔线） |
| `telegram` | str | Telegram MarkdownV2（特殊字符转义） |
| `feishu` | list[dict] | 飞书交互式卡片数组（每篇一张卡片） |
| `qq` | str | QQ 文本格式 |
| `wechat` | str | 微信文本格式 |

## 8. 知识库交互模块 (KnowledgeBot)

### 8.1 架构

`bot/knowledge_bot.py` 提供基于规则的意图识别、全文检索、订阅管理与三级权限控制。

```
KnowledgeBot.handle_message(user_id, text)
  ├── recognize_intent(text)                 # 意图识别（规则匹配）
  ├── PermissionManager.has_permission()     # 权限检查
  ├── _handle_search     → KnowledgeSearchEngine.search()
  ├── _handle_today      → KnowledgeSearchEngine.get_today()
  ├── _handle_top        → KnowledgeSearchEngine.get_top()
  ├── _handle_subscribe  → SubscriptionManager.add()
  ├── _handle_unsubscribe → SubscriptionManager.remove()
  ├── _handle_mysubs     → SubscriptionManager.get()
  └── _handle_help
```

### 8.2 组件说明

| 组件 | 类 | 职责 |
|------|-----|------|
| 搜索引擎 | `KnowledgeSearchEngine` | 从 `knowledge/articles/` 加载全量文章，支持关键词、标签、日期范围、分类过滤 |
| 订阅管理 | `SubscriptionManager` | 用户订阅 CRUD，持久化到 `knowledge/subscriptions.json` |
| 权限控制 | `PermissionManager` | READ / WRITE / DELETE 三级权限，持久化到 `knowledge/permissions.json` |
| 机器人入口 | `KnowledgeBot` | 整合以上模块，暴露 `handle_message(user_id, text) → str` |

### 8.3 意图识别

`recognize_intent(text)` 纯规则匹配（无 LLM 调用），两层优先级：

1. **命令前缀优先** — `/search` `/today` `/top` `/subscribe` `/unsubscribe` `/mysubs` `/help`
2. **自然语言回退** — 关键词匹配顺序：取消订阅 > 我的订阅 > 今天/简报 > 热门 > 订阅 > 搜索

返回 `(Intent, 参数字符串)`，Intent 枚举：`SEARCH` / `TODAY` / `TOP` / `SUBSCRIBE` / `UNSUBSCRIBE` / `MYSUBS` / `HELP` / `UNKNOWN`

### 8.4 命令用法

| 命令 | 示例 | 权限 |
|------|------|------|
| `/search` | `/search langchain #agent @agent-framework from:2026-05-01` | READ |
| `/today` | `/today 5` | READ |
| `/top` | `/top 7 10` | READ |
| `/subscribe` | `/subscribe llm #agent @research` | WRITE |
| `/unsubscribe` | `/unsubscribe` | WRITE |
| `/mysubs` | `/mysubs` | READ |
| `/help` | `/help` | — |

搜索参数语法：`关键词 #tag @分类 from:日期 to:日期 limit:数量`

### 8.5 权限模型

| 权限 | 枚举值 | 操作示例 |
|------|--------|----------|
| READ | `Permission.READ` | 搜索、查看今日/热榜、查看订阅 |
| WRITE | `Permission.WRITE` | 创建/取消订阅 |
| DELETE | `Permission.DELETE` | 删除知识条目（预留） |

首次交互时自动为用户授予 READ 权限（`grant_default_read()`），WRITE / DELETE 需手动 `grant()`。

## 9. 红线（绝对禁止）

1. **禁止** 在代码或配置文件中硬编码任何 API Key、Token、密码或密钥（使用 `.env` + 环境变量）
2. **禁止** 在未经用户明确指示的情况下提交 `git commit` 或推送代码
3. **禁止** 使用裸 `print()` 输出业务日志（统一使用 `logging` 模块）
4. **禁止** 绕过 AI 分析直接将原始抓取内容推送给用户
5. **禁止** 采集或分发任何违反相关法律法规的内容
6. **禁止** 未经用户确认修改 `knowledge/` 下已有的历史数据（只增不改、误删需确认）
7. **禁止** 在 Agent 流程中引入未定义的外部依赖（新依赖需先更新 `pyproject.toml` / `requirements.txt`）
