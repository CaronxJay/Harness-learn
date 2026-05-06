# AGENTS.md — AI 知识库助手

## 1. 项目概述

AI 知识库助手是一个自动化技术情报管线：从 GitHub Trending 等渠道采集 AI/LLM/Agent 领域的每日技术动态，经 AI 分析、摘要、去重后结构化为 JSON 知识条目存入本地知识库，最终通过 Telegram / 飞书等渠道完成多平台分发，帮助团队高效追踪 AI 领域前沿。

> **当前阶段**：核心管线（采集 → 分析 → 整理）已通过 OpenCode Sub-Agent 系统完成端到端测试验证，产出 30 条结构化知识条目覆盖 2026-05-04 和 2026-05-05 两个日期。Agent 定义（`.opencode/agents/*.md`）和 Skill 定义（`.opencode/skills/*/SKILL.md`）均已就绪。测试中发现的问题与改进建议记录于 `sub-agent-test-log.md`。Python 脚本化和 LangGraph 工作流编排为下一步规划。

## 2. 技术栈

| 层面       | 技术                                                   |
| ---------- | ------------------------------------------------------ |
| 语言       | Python 3.12（规划）；当前通过 OpenCode Skill 驱动      |
| Agent 调度 | OpenCode + Deepseek V4 Pro                             |
| Agent 运行时 | `@opencode-ai/plugin` 1.14.33（`.opencode/package.json`） |
| 技能引擎   | `.opencode/skills/` — SKILL.md 格式的技能定义；外部技能通过 `skills-lock.json` 锁定版本 |
| Agent 定义 | `.opencode/agents/` — `.md` 文件定义角色、权限、流程   |
| 多端接入   | OpenClaw（Telegram / 飞书 Bot 网关，规划中）           |
| 存储       | 本地 JSON（knowledge/raw/ → knowledge/articles/）     |
| 依赖管理   | pip + requirements.txt（规划中）                       |
| 版本控制   | Git                                                    |

## 3. 编码规范

以下规范适用于项目中所有 `.py` 文件（目前规划中）：

- **PEP 8**：用 `ruff` 全量检查。
- **snake_case**：变量、函数、文件名一律使用 `snake_case`。
- **Google 风格 docstring**：公开函数/类必须包含 `Args:`、`Returns:`、`Raises:` 段落。
- **禁止裸 `print()`**：统一使用 `logging` 模块输出日志；非日志类终端输出走 `rich` 或专用 `console` 工具。
- **类型注解**：函数签名必须包含完整的参数和返回值类型注解。
- **异常处理**：禁止裸露的 `except:`，必须指定异常类型或使用 `except Exception as e:` 并记录日志。

## 4. 项目结构

```
.
├── AGENTS.md                          # 本文件
├── skills-lock.json                   # 外部技能版本锁定（GitHub 来源技能）
├── sub-agent-test-log.md              # Sub-Agent 端到端测试日志与改进建议
├── specs/
│   └── project-vision.md              # 项目愿景、验收标准与验证方式
├── .opencode/
│   ├── .gitignore                     # OpenCode 插件 gitignore
│   ├── package.json                   # @opencode-ai/plugin 依赖
│   ├── package-lock.json
│   ├── node_modules/                  # 插件依赖（uuid, msgpackr 等）
│   ├── agents/                        # Agent 角色定义（.md 文件）
│   │   ├── collector.md               # 采集 Agent — 完整行为定义与权限
│   │   ├── analyzer.md                # 分析 Agent — 完整行为定义与权限
│   │   └── organizer.md              # 整理 Agent — 完整行为定义与权限
│   ├── skills/                        # 可复用技能定义（SKILL.md）
│   │   ├── github-trending/
│   │   │   └── SKILL.md               # GitHub Trending 采集技能（7 步流程）
│   │   ├── arxiv-papers/
│   │   │   └── SKILL.md               # arXiv 论文采集技能（7 步流程）
│   │   └── tech-summary/
│   │       └── SKILL.md               # 技术深度分析技能（4 步流程）
│   └── logs/                          # Agent 执行日志（规划中）
├── knowledge/
│   ├── raw/                           # 原始采集数据
│   │   └── {source}-{YYYY-MM-DD}.json
│   └── articles/                      # 结构化知识条目
│       ├── {YYYY-MM-DD}-{source}-{slug}.json    # 单个知识条目
│       └── tech-summary-{YYYY-MM-DD}.json       # 每日分析汇总（含趋势发现）
├── pipelines/                         # LangGraph 工作流定义（规划中）
│   ├── daily_pipeline.py
│   └── adhoc_pipeline.py
├── utils/                             # 通用工具（规划中）
│   ├── logging_config.py
│   └── storage.py
├── tests/                             # 单元测试 & 集成测试（规划中）
└── requirements.txt                   # Python 依赖（规划中）
```

### 文件命名规范

| 文件类型           | 命名格式                                                | 示例                                            |
| ------------------ | ------------------------------------------------------- | ----------------------------------------------- |
| 原始采集数据       | `knowledge/raw/{source}-{YYYY-MM-DD}.json`              | `github-trending-2026-05-05.json`               |
| 分析汇总           | `knowledge/articles/tech-summary-{YYYY-MM-DD}.json`     | `tech-summary-2026-05-05.json`                  |
| 单条知识条目       | `knowledge/articles/{YYYY-MM-DD}-{source}-{slug}.json`  | `2026-05-05-github-aattaran-deepclaude.json`    |

> **slug 生成规则**：从 owner/repo 提取，全小写、用连字符替换非字母数字字符、限制 50 字符。

## 5. 知识条目 JSON 格式

单条知识条目标准格式：

```json
{
    "id": "2026-05-05-003",
    "title": "DeepClaude：Claude Code 低成本多后端代理方案",
    "source": "github",
    "source_url": "https://github.com/aattaran/deepclaude",
    "summary": "DeepClaude 是一个本地代理，截获 Claude Code 的 /v1/messages 请求并路由至 DeepSeek V4 Pro…",
    "highlights": [
        "本地代理截获 Claude Code API 请求并路由至 DeepSeek V4 Pro/OpenRouter/Fireworks AI",
        "成本降幅 94%：$0.87/M vs Anthropic $15/M"
    ],
    "score": 8,
    "score_reason": "直接解决 Agent 编码工具成本痛点，方案简洁可立即用于生产。",
    "tags": ["agent", "code-generation", "llm", "open-source"],
    "status": "published",
    "fetched_at": "2026-05-05T04:11:06Z",
    "analyzed_at": "2026-05-05T04:17:54Z",
    "published_at": "2026-05-05T04:17:54Z",
    "metadata": {
        "stars": 1076,
        "stars_today": null,
        "language": "JavaScript",
        "hackernews_points": null,
        "hackernews_comments": null
    }
}
```

| 字段              | 类型          | 说明                                                   |
| ----------------- | ------------- | ------------------------------------------------------ |
| `id`              | `str`         | 唯一标识，格式 `YYYY-MM-DD-NNN`                        |
| `title`           | `str`         | 项目标题（≤30 字）                                     |
| `source`          | `str`         | 来源渠道：`"github"` / `"hackernews"` / `"arxiv"`      |
| `source_url`      | `str`         | 原始链接                                               |
| `summary`         | `str`         | AI 生成的中文摘要（≤200 字）                           |
| `highlights`      | `list[str]`   | 技术亮点（2-3 条，事实驱动）                           |
| `score`           | `int`         | 综合评分（1-10），每批 9-10 分不超过 2 个              |
| `score_reason`    | `str`         | 评分理由（一句话）                                     |
| `tags`            | `list[str]`   | 分类标签，如 `["llm", "agent", "open-source"]`        |
| `status`          | `str`         | `"raw"` → `"analyzed"` → `"published"` → `"archived"` |
| `fetched_at`      | `str` (ISO)   | 采集时间戳（UTC）                                      |
| `analyzed_at`     | `str` (ISO)   | 分析完成时间戳（UTC）                                  |
| `published_at`    | `str` (ISO)   | 发布/整理时间戳（UTC）                                 |
| `metadata`        | `dict`        | 源数据元信息（stars、language、hackernews 数据等）     |

### tech-summary 格式（每日分析汇总）

```json
{
    "source": "tech-summary",
    "analyzed_at": "2026-05-05T04:17:54Z",
    "input_files": ["knowledge/raw/github-trending-2026-05-05.json"],
    "items": [
        // 同知识条目 JSON，使用 name/url 代替 id/source_url
    ],
    "trends": [
        {
            "topic": "趋势主题描述",
            "projects": ["owner/repo1", "owner/repo2"],
            "new_concepts": []
        }
    ]
}
```

### 评分标准

| 分数区间 | 含义                                 |
| -------- | ------------------------------------ |
| 9-10     | 改变格局：可能重塑领域技术路线       |
| 7-8      | 直接有帮助：可立即用于生产或研究     |
| 5-6      | 值得了解：有亮点但落地尚早或场景窄   |
| 1-4      | 可略过：同质化严重或无明显增量价值   |

### 标签池

`llm`、`agent`、`multimodal`、`rag`、`open-source`、`fine-tuning`、`embedding`、`vector-db`、`inference`、`tool-use`、`evaluation`、`safety`、`alignment`、`prompt-engineering`、`reasoning`、`code-generation`、`workflow`、`framework`、`benchmark`、`dataset`、`deployment`、`vision`、`audio`、`robotics`

## 6. Agent 角色与技能映射

管线通过 3 个 Sub-Agent 角色协作完成，各自有独立的权限约束与执行流程。Agent 定义文件位于 `.opencode/agents/`。

| 角色              | 定义文件                   | 负责环节 | 允许工具                          | 禁止工具     | 调用技能                              |
| ----------------- | -------------------------- | -------- | --------------------------------- | ------------ | ------------------------------------- |
| **采集 Agent**    | `agents/collector.md`      | 数据采集 | Read, Grep, Glob, WebFetch        | Write        | `github-trending`, `arxiv-papers`     |
| **分析 Agent**    | `agents/analyzer.md`       | AI 分析  | Read, Grep, Glob, WebFetch        | Write        | `tech-summary`                        |
| **整理 Agent**    | `agents/organizer.md`      | 审核归档 | Read, Grep, Glob, Write, Edit     | WebFetch     | —（内联逻辑）                         |

### 各 Agent 职责概要

#### 采集 Agent（collector）

- **数据源**：GitHub Search API（近 7 天 AI/LLM/Agent 仓库，按 stars 降序）、Hacker News Top Stories
- **采集策略**：关键词过滤 + topics 过滤，排除 Awesome 列表和教程类仓库
- **输出**：`knowledge/raw/github-trending-{date}.json`、`knowledge/raw/hackernews-top-{date}.json`
- **关键约束**：禁止 Write 工具 — 采集结果返回给主 Agent，由主 Agent 委派 Organizer 写入

#### 分析 Agent（analyzer）

- **输入**：`knowledge/raw/` 下当天所有 JSON 文件
- **分析内容**：中文技术摘要（100-200 字）、技术亮点（2-3 条）、综合评分（1-10）、标签（3-5 个）、评分理由
- **评分维度**：技术深度(0.25)、实用价值(0.30)、时效性(0.20)、社区热度(0.15)、领域匹配(0.10) → 最终量化为 1-10 整数
- **趋势发现**：汇总本批分析结果，识别 2-5 条宏观趋势
- **输出**：追加分析字段到每个条目 + 趋势发现
- **关键约束**：禁止 Write 工具，分析结果返回给主 Agent

#### 整理 Agent（organizer）

- **输入**：分析 Agent 输出（含 `analyzed_at` 的条目）
- **处理流程**：必填字段验证 → 质量过滤（score < 6 或 summary < 50 字 → 丢弃）→ 去重（source_url 精确匹配）→ 格式化 → 写入独立文件
- **输出**：`knowledge/articles/{date}-{source}-{slug}.json` 标准知识条目 + 分发指令摘要
- **关键约束**：禁止 WebFetch 工具（不应再去外部获取数据）；状态流转 `analyzed → published`

### 管线执行流程

```
@collector → skill:github-trending → raw JSON（对话中返回给主 Agent）
       ↓   (主 Agent 委派 Organizer 写入)
       knowledge/raw/github-trending-{date}.json
       ↓
@analyzer  → skill:tech-summary → 分析结果（对话中返回给主 Agent）
       ↓   (主 Agent 委派 Organizer 写入)
       knowledge/articles/tech-summary-{date}.json
       ↓
@organizer → 去重 + 格式化 + 写入
       ↓
       knowledge/articles/{date}-{source}-{slug}.json (×N)
```

> **权限委托模式**：采集和分析 Agent 均禁止 Write，分析结果通过主 Agent 中转，由整理 Agent 统一写入。这确保采集/分析环节的纯读取安全隔离。

### Agent 命令日志格式

每个 Agent 执行后在 `.opencode/logs/`（规划中）下生成日志：

```
.opencode/logs/{YYYY-MM-DD}/{agent_name}.log
```

日志包含：开始时间、结束时间、处理的条目数、成功/失败条数、异常信息。

## 7. 外部技能管理

项目通过 `skills-lock.json` 锁定从 GitHub 社区引入的技能版本：

| 技能         | 来源仓库              | 用途                         |
| ------------ | --------------------- | ---------------------------- |
| `grill-me`   | `mattpocock/skills`   | 设计方案压力测试与评审       |
| `to-issues`  | `mattpocock/skills`   | 将计划/PRD 分解为独立 Issue  |

外部技能与本地技能（`github-trending`、`arxiv-papers`、`tech-summary`）共同构成完整的技能体系。

## 8. 红线（绝对禁止的操作）

1. **禁止硬编码 Token/API Key**：所有密钥通过环境变量或 `.env` 文件注入，且 `.env` 必须加入 `.gitignore`。
2. **禁止提交含密钥的文件**：包括但不限于 `.env`、`credentials.json`、`service_account.json` 等，防检规则写在 `.gitignore` 和 pre-commit hook 中。
3. **禁止未经去重直接发布**：整理阶段必须先按 `source_url` 精确去重，避免同一信息重复推送。
4. **禁止绕过状态机直接修改 `status` 字段**：状态流转必须遵循 `raw → analyzed → published → archived`，不允许跳转或回退。
5. **禁止在采集/分析环节直接调用分发通道**：分发只能由「整理 Agent」统一执行，采集和分析 Agent 不得持有 Bot token。
6. **禁止在生产代码中使用裸 `print()`**：统一使用 `logging` 模块。
7. **禁止 `git push --force` 到 main/master 分支**：仅允许在个人 Feature 分支上使用 force push。
8. **禁止未经 pytest 全部通过即合并 PR**：CI 中强制运行 `pytest && ruff check .`（规划中）。

## 9. 重要参考文档

| 文档                 | 路径                            | 用途                                           |
| -------------------- | ------------------------------- | ---------------------------------------------- |
| 项目愿景与验收标准   | `specs/project-vision.md`       | 功能性/质量/渠道验收标准，CI 层定义             |
| Sub-Agent 测试日志   | `sub-agent-test-log.md`         | 全链路测试记录，发现的问题与改进建议           |
| 采集 Agent 定义      | `.opencode/agents/collector.md` | 采集 Agent 完整行为、权限、数据源、输出格式     |
| 分析 Agent 定义      | `.opencode/agents/analyzer.md`  | 分析 Agent 维度评分公式、摘要质量、分析原则     |
| 整理 Agent 定义      | `.opencode/agents/organizer.md` | 整理 Agent 过滤规则、去重策略、索引维护规则     |
| GitHub Trending 技能 | `.opencode/skills/github-trending/SKILL.md`  | 7 步采集流程 — 搜索→提取→过滤→去重→摘要→排序→输出 |
| arXiv 论文技能       | `.opencode/skills/arxiv-papers/SKILL.md`    | 7 步采集流程 — 查询→API→解析→过滤→去重→摘要→输出 |
| 技术分析技能         | `.opencode/skills/tech-summary/SKILL.md`    | 4 步分析流程 — 读取→逐条分析→趋势发现→输出      |
| 外部技能锁           | `skills-lock.json`              | 外部技能（mattpocock/skills）的版本与完整性锁定 |
