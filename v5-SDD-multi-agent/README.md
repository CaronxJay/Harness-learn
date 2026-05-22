# AI 知识库系统

> 基于多 Agent 协作的 AI 技术知识库 — 自动采集、智能分析、定时推送

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        📡 分发层                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │Telegram  │  │  飞书     │  │  QQ Bot  │  │  微信    │        │
│  │MarkdownV2│  │交互式卡片 │  │ Markdown │  │ Markdown │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                         ▲                                        │
│         KnowledgeBot (交互查询 / 订阅 / 权限)                      │
├─────────────────────────────────────────────────────────────────┤
│                        ⚙️ 工程层                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │Validate  │  │ Quality  │  │ PII 掩码 │  │CostGuard │        │
│  │JSON 校验 │  │ 质量评分 │  │ 安全过滤 │  │ 预算熔断 │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
├─────────────────────────────────────────────────────────────────┤
│                      🔄 Pipeline 层                              │
│                   LangGraph StateGraph                           │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐                     │
│  │ plan │──→│collect│──→│analyze│──→│review│                     │
│  └──────┘   └──────┘   └──────┘   └──┬───┘                     │
│                     ┌────────────────┼────┐                      │
│                     │ ✓ passed       │ ✗ (iter<3)               │
│                     ▼                ▼                           │
│              ┌─────────┐     ┌─────────┐                        │
│              │ organize │     │ revise  │──→ review (loop)       │
│              └────┬─────┘     └─────────┘                        │
│                   │   ✗ (iter≥3)                                │
│                   ▼         ▼                                   │
│              ┌────────┐ ┌────────────┐                           │
│              │  save  │ │ human_flag │                           │
│              └────────┘ └────────────┘                           │
├─────────────────────────────────────────────────────────────────┤
│                      🧠 Agent 层                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │Collector │  │ Analyzer │  │Organizer │   OpenCode Sub-Agent  │
│  │GitHub/arXiv│ │摘要/评分 │  │去重/归档 │   + Skill 技能库      │
│  └──────────┘  └──────────┘  └──────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

**4 层架构：**

| 层级 | 职责 | 核心组件 |
|------|------|----------|
| **Agent 层** | 角色定义与 Prompt 工程 | Collector / Analyzer / Organizer，Skill 技能库 |
| **Pipeline 层** | 8 节点工作流编排 | LangGraph StateGraph，审核-修正循环，HumanFlag 兜底 |
| **工程层** | 质量保障与成本控制 | JSON 校验、5 维度质量评分、PII 掩码、CostGuard 预算熔断 |
| **分发层** | 多渠道推送与交互查询 | Telegram / 飞书 / QQ Bot / 企业微信，KnowledgeBot 规则引擎 |

---

## 快速开始

### 1. Clone

```bash
git clone https://github.com/CaronxJay/ai-knowledge-base.git
cd ai-knowledge-base
# 所有代码在 v4-production/ 目录下
cd v4-production
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入以下必填项：
```

```ini
# LLM (至少选一个)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

# 可选：推送渠道
AppID=          # QQ Bot
AppSecret=      # QQ Bot
QQ_TARGET_ID=   # QQ Bot
chat_id=        # 微信
```

### 3. 运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行完整流水线
python pipeline/pipeline.py --sources github,rss --limit 20

# 启动交互查询（可选）
python bot/knowledge_bot.py
```

---

## 目录结构

| 目录 / 文件 | 说明 | 版本 |
|-------------|------|------|
| `v1-skeletion/` | 骨架版本：OpenCode Sub-Agent 定义 + Skill 技能库 | V1 |
| `v2-automation/` | 自动化版本：Python CLI 流水线 + crontab 定时 | V2 |
| `v3-multi-agent/` | 多 Agent 版本：LangGraph 8 节点工作流 + 审核循环 | V3 |
| `v4-production/` | **生产版本 (当前)**：全功能集成 + 四渠道推送 + KnowledgeBot | V4 |
| `v4-production/pipeline/` | 独立流水线：采集 → 分析 → 整理 → 保存 | V4 |
| `v4-production/workflows/` | LangGraph 工作流：StateGraph + 8 节点定义 | V4 |
| `v4-production/distribution/` | 推送模块：Formatter + Publisher (QQ / 飞书 / Telegram / 微信) | V4 |
| `v4-production/bot/` | 交互查询：KnowledgeBot + SearchEngine + 订阅 + 权限 | V4 |
| `v4-production/hooks/` | 质量工具：JSON 校验 + 5 维度质量评分 | V4 |
| `v4-production/patterns/` | Agent 设计模式：Supervisor 监督 / Router 路由 | V3 |
| `v4-production/tests/` | 测试套件：CostGuard / Security / Eval / Injection | V3 |
| `v4-production/openclaw/` | OpenClaw 网关集成 | V4 |
| `v4-production/knowledge/` | 知识数据：raw / articles / reports / pending_review | V4 |
| `v4-production/.github/` | CI 工作流：每日自动采集 + 质量检测 + 自动提交 | V4 |
| `v4-production/requirements.txt` | 依赖清单：httpx + langgraph + aiohttp | V4 |
| `v4-production/.env.example` | 环境变量模板 | V4 |
| `v4-production/opencode.json` | OpenCode 配置（MCP Server 注册） | V4 |

---

## 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Agent 编排 | **OpenCode** | Sub-Agent 角色定义 + Skill 技能库 + MCP Server |
| 工作流引擎 | **LangGraph** | StateGraph，8 节点有状态流水线，条件路由 |
| 大模型 | **DeepSeek** (V3/V4) | 默认提供商，¥0.27/M tokens 输入 |
| LLM 客户端 | pipeline/model_client.py | 多提供商兼容 + 指数退避重试 + JSON 强制输出 |
| 消息推送 | **QQ Bot API** (v2) | msg_type=2 Markdown，access_token 缓存 |
| 消息推送 | **飞书 Webhook** | 交互式卡片，单篇推送 |
| 消息推送 | **Telegram Bot API** | MarkdownV2 格式 |
| 消息推送 | **企业微信 API** | 应用消息，Markdown 格式 |
| HTTP 客户端 | httpx / aiohttp | 异步请求，API 调用 |
| 质量保障 | hooks/ + CostGuard | 5 维度审核、注入清洗、PII 掩码、预算熔断 |
| CI/CD | GitHub Actions | 每日 UTC 08:00 自动采集 → 分析 → 校验 → 提交 |

---

## 版本历史

| 版本 | 阶段 | 核心能力 |
|------|------|----------|
| **V1** | 骨架 (Skeleton) | OpenCode Sub-Agent 角色定义 (Collector / Analyzer / Organizer)；Skill 技能库 (github-trending / arxiv-papers / tech-summary)；知识条目 JSON 格式规范；1-10 分评分标准 |
| **V2** | 自动化 (Automation) | Python 全 Pipeline CLI (`pipeline.py`)；LLM 客户端多提供商 (DeepSeek / Qwen / OpenAI)；crontab 定时调度；MCP Knowledge Server；CostTracker 成本报告；`--step` 分步运行 |
| **V3** | 多 Agent (Multi-Agent) | LangGraph 8 节点 StateGraph (plan → collect → analyze → review → revise → organize → save → human_flag)；5 维度加权 LLM 审核 (阈值 7.0)；审核-修正循环 (最多 3 轮)；CostGuard 预算熔断；3 档采集策略 (lite/standard/full)；Agent 设计模式库 (Supervisor / Router)；安全模块 (注入清洗 + PII 掩码) |
| **V4** | 生产 (Production) | KnowledgeBot 规则意图识别 + 全文搜索 + 订阅管理 + 三级权限；四渠道日报推送 (Telegram / 飞书 / QQ / 企业微信)；5 种消息格式转换器；OpenClaw 网关集成；GitHub Actions 全自动 CI |

---

## 月度成本估算

> 基于每日 20 篇文章的全链路处理 (采集 → 分析 → 审核 → 修正)，含 1 轮审核 + 1 轮修正估算。

| 提供商 | 模型 | 输入价格 | 输出价格 | 日消耗 * | **月成本** |
|--------|------|----------|----------|----------|------------|
| **DeepSeek** | deepseek-chat | ¥0.27 / 百万 token | ¥1.10 / 百万 token | ~¥0.08 | **≈ ¥2.4** |
| Qwen | qwen-plus | ¥0.40 / 百万 token | ¥1.20 / 百万 token | ~¥0.12 | **≈ ¥3.6** |
| OpenAI | gpt-4o | ¥2.50 / 百万 token | ¥10.00 / 百万 token | ~¥0.80 | **≈ ¥24.0** |

> *日消耗为估算值，包含：单篇分析 (~2000 in, ~500 out)、批量审核 (~4000 in, ~500 out)、修正 (~4000 in, ~500 out)，总计约 48K 输入 + 15K 输出 token/天。*

**推荐配置：** DeepSeek，月度成本可控制在 **¥2.5 以内**。可配合 `BUDGET_YUAN` 环境变量设置熔断上限。

---

## QQ bot 已通过测试截图
<img width="605" height="554" alt="qq bot" src="https://github.com/user-attachments/assets/2ae6b7fb-6718-46e1-9c93-90d351a6f75f" />

MIT © 2026
