# AGENTS.md — AI 知识库助手

## 项目概述

自动采集 GitHub Trending、Hacker News 等渠道的 AI/LLM/Agent 技术动态，经 AI 分析后结构化存储为 JSON，并支持多渠道分发（QQBot、飞书）。

## 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.12 |
| AI 平台 | OpenCode + DeepSeek |
| Agent 框架 | LangGraph |
| 工具调用 | OpenClaw |
| 依赖管理 | pip + requirements.txt |

## 编码规范

- 遵循 **PEP 8**
- 命名：`snake_case`（变量、函数、模块），`PascalCase`（类）
- 文档字符串：**Google 风格**
- **禁止裸 `print()`**，必须使用 `logging` 模块
- 类型注解：所有公开函数必须添加

## 项目结构

```
/
├── .opencode/
│   ├── agents/          # Agent 定义
│   └── skills/          # Skill 定义
│       ├── github-trending/   # GitHub Trending 数据源
│       ├── hackernews/        # Hacker News 数据源
│       ├── ai-filter/         # AI 内容过滤
│       ├── deepseek-analyzer/ # DeepSeek 分析
│       ├── content-summarizer/ # 内容摘要
│       ├── quality-evaluator/ # 质量评估
│       ├── tag-generator/     # 标签生成
│       ├── dedup-checker/     # 去重检查
│       ├── json-formatter/    # JSON 格式化
│       └── file-archiver/     # 文件存档
├── knowledge/
│   ├── raw/             # 原始采集数据
│   ├── articles/        # 分析后的知识条目
│   ├── pending_review/  # 待人工审核的条目
│   └── index.json       # 知识条目索引
├── workflows/           # LangGraph 工作流（核心）
│   ├── state.py         # KBState 共享状态定义
│   ├── graph.py         # 工作流图编排
│   ├── nodes.py         # 核心节点（collect/analyze/organize/review/save）
│   ├── planner.py       # 策略规划节点
│   ├── reviser.py       # 审核反馈修改节点
│   ├── human_flag.py    # 人工介入兜底节点
│   └── model_client.py  # LLM 客户端 + CostGuard 集成
├── tests/               # 测试 + 运行时模块
│   ├── cost_guard.py    # 预算守卫（被 workflows 依赖）
│   ├── security.py      # 安全防护（被 workflows 依赖）
│   ├── eval_test.py     # LLM 质量评估测试
│   └── test_*.py        # 其他单元测试
├── pipeline/            # LLM 客户端底层实现
├── src/                 # 源代码（核心模块）
├── specs/               # 项目文档
├── AGENTS.md            # 本文件
└── requirements.txt
```

## 工作流架构（LangGraph）

```
collect → analyze → organize → review
                    ↑              │
                    └──────────────┘
                               ├─ (通过) → save → END
                               ├─ (不通过, iteration<3) → revise → review（循环）
                               └─ (不通过, iteration>=3) → human_flag → END
```

### 核心节点

| 节点 | 文件 | 职责 | 安全接入点 |
|------|------|------|-----------|
| `planner_node` | `planner.py` | 三档策略规划（lite/standard/full） | - |
| `collect_node` | `nodes.py` | GitHub API 采集 | `sanitize_input` 防注入 |
| `analyze_node` | `nodes.py` | LLM 生成摘要/标签/评分 | - |
| `organize_node` | `nodes.py` | 过滤/去重/PII 掩码 | `filter_output` 防泄露 |
| `review_node` | `nodes.py` | LLM 五维度审核 | - |
| `revise_node` | `reviser.py` | 根据反馈批量修改 | - |
| `save_node` | `nodes.py` | 写盘 + 更新索引 | - |
| `human_flag_node` | `human_flag.py` | 人工介入兜底 | - |

### KBState 共享状态

```python
class KBState(TypedDict):
    plan: dict              # Planner 策略
    sources: list[dict]     # 原始采集数据
    analyses: list[dict]    # LLM 分析结果
    articles: list[dict]    # 最终知识条目
    review_feedback: str    # 审核反馈
    review_passed: bool     # 审核是否通过
    iteration: int          # 当前迭代次数
    needs_human_review: bool
    cost_tracker: dict      # Token 成本追踪
```

### Planner 策略

| 档位 | target | per_source_limit | relevance_threshold | max_iterations |
|------|--------|------------------|---------------------|----------------|
| lite | <10 | 5 | 0.7 | 1 |
| standard | 10-19 | 10 | 0.5 | 2 |
| full | ≥20 | 20 | 0.4 | 3 |

## 安全防护（tests/security.py）

两道防线，分别卡在数据流的入口和出口：

| 接入点 | 位置 | 防护目标 | 机制 |
|--------|------|---------|------|
| `sanitize_input` | collect 出口 | OWASP LLM #1 Prompt 注入 | 21 个正则（10英文+11中文）+ 控制字符清除 + 长度截断 |
| `filter_output` | organize 出口 | PII 泄露（手机/邮箱/身份证/信用卡/IP） | 5 类 PII 正则 + `[TYPE_MASKED]` 替换 |

附加能力：
- `RateLimiter`：滑动窗口限流（默认 60次/分钟）
- `AuditLogger`：全链路审计日志

## 成本控制（tests/cost_guard.py）

三重保护机制：

```
chat()/chat_json() → guard.record() → guard.check()
                                           │
                                 ┌─────────┼─────────┐
                                 ▼         ▼         ▼
                               ok(<80%)  warning   exceeded(≥100%)
                                          (≥80%)    抛 BudgetExceededError
```

- 每次 LLM 调用自动记录 token 用量和成本
- 节点通过 `node_name` 参数归类成本（analyze/review/revise/organize）
- 超预算自动熔断，工作流停止
- 结束时输出成本报告并落盘到 `knowledge/cost-report.json`

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

## Agent 角色概览

| 角色 | 职责 | 输入 | 输出 |
|------|------|------|------|
| Planner | 策略规划 | 目标采集量 | plan dict |
| Collector | GitHub API 采集 + 注入清洗 | plan | sources |
| Analyzer | LLM 生成摘要/标签/评分 | sources | analyses |
| Organizer | 过滤/去重/PII 掩码 | analyses, plan | articles |
| Reviewer | LLM 五维度审核 | analyses, plan | review_passed, feedback |
| Reviser | 根据反馈批量修改 | analyses, feedback | analyses（改进） |
| HumanFlag | 人工介入兜底 | analyses, iteration | pending_review/ |

## Skills 说明

| Skill | 用途 | 所属 Agent | 调用方式 |
|-------|------|------------|----------|
| github-trending | 采集 GitHub 热门项目 | 采集 Agent | `.opencode/skills/github-trending/SKILL.md` |
| hackernews | 采集 Hacker News 热帖 | 采集 Agent | `.opencode/skills/hackernews/SKILL.md` |
| ai-filter | 过滤 AI 相关内容 | 采集 Agent | `.opencode/skills/ai-filter/SKILL.md` |
| deepseek-analyzer | 调用 DeepSeek 分析项目 | 分析 Agent | `.opencode/skills/deepseek-analyzer/SKILL.md` |
| content-summarizer | 生成中文摘要 | 分析 Agent | `.opencode/skills/content-summarizer/SKILL.md` |
| quality-evaluator | 评估项目质量等级 | 分析 Agent | `.opencode/skills/quality-evaluator/SKILL.md` |
| tag-generator | 生成技术标签 | 分析 Agent | `.opencode/skills/tag-generator/SKILL.md` |
| dedup-checker | 检查数据重复 | 整理 Agent | `.opencode/skills/dedup-checker/SKILL.md` |
| json-formatter | 格式化为标准 JSON | 整理 Agent | `.opencode/skills/json-formatter/SKILL.md` |
| file-archiver | 将结果存档到指定目录 | 整理 Agent | `.opencode/skills/file-archiver/SKILL.md` |

## 运行方式

```bash
# 执行完整工作流
python -m workflows.graph

# 运行测试（跳过 LLM 调用）
pytest tests/ -v -k "not slow"

# 运行测试（包含 LLM 调用）
pytest tests/ -v --runslow

# 运行成本守卫自测
python tests/cost_guard.py

# 运行安全模块自测
python tests/security.py
```

## 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `BUDGET_YUAN` | LLM 调用总预算（元） | 1.0 |
| `PLANNER_TARGET_COUNT` | 目标采集量 | 10 |
| `GITHUB_TOKEN` | GitHub API Token（可选，提升速率限制） | - |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | - |

## 红线

- **禁止**提交任何密钥、Token、API Key 到仓库
- **禁止**裸 `print()` 输出调试信息
- **禁止**硬编码路径或配置
- **禁止**跳过错误处理直接 `except: pass`
- **禁止**在 Agent 中执行任意代码（沙箱外）
