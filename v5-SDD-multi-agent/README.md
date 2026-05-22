# AI 知识库

自动采集 GitHub Trending 和 Hacker News 的 AI/LLM/Agent 技术动态，经 DeepSeek AI 分析后结构化存储为 JSON，支持多渠道分发（QQBot、飞书）。

## 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.12 |
| AI 平台 | OpenCode + DeepSeek |
| Agent 框架 | LangGraph |
| 工具调用 | OpenClaw |
| 依赖管理 | pip + requirements.txt |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入 API Key：

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `GITHUB_TOKEN` | GitHub API Token | - |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | - |
| `BUDGET_YUAN` | LLM 调用总预算（元） | 1.0 |
| `PLANNER_TARGET_COUNT` | 目标采集量 | 10 |

### 3. 运行

```bash
# 执行完整工作流
python -m workflows.graph

# 运行测试（跳过 LLM 调用）
pytest tests/ -v -k "not slow"

# 运行测试（包含 LLM 调用）
pytest tests/ -v --runslow
```

## 项目结构

```
v5-SDD-multi-agent/
├── .github/workflows/daily.yml   # GitHub Actions 定时任务
├── .opencode/
│   ├── agents/                    # Agent 角色定义
│   ├── skills/                    # Skill 定义（数据源、分析、格式化等）
│   └── commands/                  # OpenSpec 命令
├── knowledge/
│   ├── raw/                       # 原始采集数据
│   ├── articles/                  # 分析后的知识条目
│   └── pending_review/            # 待人工审核条目
├── workflows/                     # LangGraph 工作流（核心）
│   ├── state.py                   # KBState 共享状态定义
│   ├── graph.py                   # 工作流图编排
│   ├── nodes.py                   # 核心节点
│   ├── planner.py                 # 策略规划节点
│   ├── reviser.py                 # 审核反馈修改节点
│   ├── human_flag.py              # 人工介入兜底节点
│   └── model_client.py            # LLM 客户端 + CostGuard 集成
├── src/                           # 核心模块
│   ├── analyzer.py                # 分析器
│   ├── organizer.py               # 整理器
│   ├── error_handler.py           # 错误处理
│   └── logger.py                  # 日志模块
├── pipeline/                      # LLM 客户端底层实现
│   ├── model_client.py
│   ├── pipeline.py
│   ├── rss_loader.py
│   └── rss_sources.yaml
├── patterns/                      # Agent 模式实现
│   ├── router.py                  # Router 模式
│   └── supervisor.py              # Supervisor 模式
├── hooks/                         # Git Hooks
│   ├── check_quality.py
│   └── validate_json.py
├── tests/                         # 测试与安全模块
│   ├── cost_guard.py              # 预算守卫
│   ├── security.py                # 安全防护
│   ├── eval_test.py               # LLM 质量评估
│   └── test_*.py                  # 单元测试
├── specs/                         # 项目文档与设计规范
│   ├── issues.md                  # Issues 列表
│   ├── schemas/                   # JSON Schema
│   └── issue-*.md                 # 各 Issue 设计文档
├── openspec/                      # OpenSpec 配置
├── mcp_knowledge_server.py        # MCP 知识服务器
├── AGENTS.md                      # Agent 开发指南
├── README.md                      # 本文件
├── requirements.txt               # Python 依赖
├── .env.example                   # 环境变量示例
├── .gitignore
└── opencode.json
```

## 工作流架构（LangGraph）

```
collect -> analyze -> organize -> review
                   ↑              │
                   └──────────────┘
                              ├─ (通过) -> save -> END
                              ├─ (不通过, iteration<3) -> revise -> review（循环）
                              └─ (不通过, iteration>=3) -> human_flag -> END
```

### 核心节点

| 节点 | 文件 | 职责 |
|------|------|------|
| `planner_node` | `planner.py` | 三档策略规划（lite/standard/full） |
| `collect_node` | `nodes.py` | GitHub/HN 采集 + 注入清洗 |
| `analyze_node` | `nodes.py` | LLM 生成摘要/标签/评分 |
| `organize_node` | `nodes.py` | 过滤/去重/PII 掩码 |
| `review_node` | `nodes.py` | LLM 五维度审核 |
| `revise_node` | `reviser.py` | 根据反馈批量修改 |
| `save_node` | `nodes.py` | 写盘 + 更新索引 |
| `human_flag_node` | `human_flag.py` | 人工介入兜底 |

### Planner 策略

| 档位 | 目标数量 | 单源上限 | 相关度阈值 | 最大迭代 |
|------|---------|---------|-----------|---------|
| lite | <10 | 5 | 0.7 | 1 |
| standard | 10-19 | 10 | 0.5 | 2 |
| full | >=20 | 20 | 0.4 | 3 |

## 输出格式

### Raw（knowledge/raw/）

```json
[
  {
    "title": "项目名称",
    "url": "https://github.com/...",
    "source": "github|hackernews",
    "popularity": 12345,
    "summary": "一句话中文摘要"
  }
]
```

### Analyzed（knowledge/articles/）

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

## 安全防护

| 接入点 | 位置 | 防护目标 | 机制 |
|--------|------|---------|------|
| `sanitize_input` | collect 出口 | Prompt 注入 | 21 个正则 + 控制字符清除 + 长度截断 |
| `filter_output` | organize 出口 | PII 泄露 | 5 类 PII 正则 + 掩码替换 |

## 成本控制

三重保护：每次 LLM 调用自动记录 token 用量，80% 预算告警，100% 熔断停止。

## 开发

### Issues 列表

详见 [specs/issues.md](specs/issues.md)。

### 代码风格

- 遵循 PEP 8
- 命名：`snake_case`（变量、函数、模块），`PascalCase`（类）
- 文档字符串：Google 风格
- 禁止裸 `print()`，必须使用 `logging` 模块
- 所有公开函数必须添加类型注解
