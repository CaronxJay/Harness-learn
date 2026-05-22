# 项目结构

```
ai-knowledge-base/
├── .github/
│   └── workflows/
│       └── daily.yml              # Issue #04: GitHub Actions workflow
├── .opencode/
│   ├── agents/
│   │   ├── collector.md           # 采集 Agent 定义
│   │   ├── analyzer.md            # 分析 Agent 定义
│   │   └── organizer.md           # 整理 Agent 定义
│   └── skills/
│       ├── github-trending/       # GitHub Trending 数据源
│       ├── hackernews/            # Hacker News 数据源
│       ├── ai-filter/             # AI 内容过滤
│       └── deepseek-analyzer/     # DeepSeek 分析
├── knowledge/
│   ├── raw/                       # Issue #01: 原始采集数据
│   │   └── YYYY-MM-DD.json
│   └── articles/                  # Issue #03: 分析后的知识条目
│       └── {date}-{source}-{slug}.json
├── logs/                          # Issue #05: 日志文件
│   └── YYYY-MM-DD.log
├── specs/
│   ├── project-vision.md          # 项目愿景
│   ├── technical-design.md        # 技术方案
│   ├── agents-prd.md              # Agent PRD
│   ├── issues.md                  # Issues 列表
│   ├── issue-01-collector.md      # Issue #01 详细说明
│   ├── issue-02-analyzer.md       # Issue #02 详细说明
│   ├── issue-03-organizer.md      # Issue #03 详细说明
│   ├── issue-04-workflow.md       # Issue #04 详细说明
│   ├── issue-05-error-handling.md # Issue #05 详细说明
│   └── schemas/
│       ├── raw.json               # Raw JSON Schema
│       └── article.json           # Article JSON Schema
├── src/
│   ├── __init__.py
│   ├── collector.py               # Issue #01: 采集 Agent 实现
│   ├── analyzer.py                # Issue #02: 分析 Agent 实现
│   ├── organizer.py               # Issue #03: 整理 Agent 实现
│   ├── github.py                  # GitHub API 调用
│   ├── hackernews.py              # Hacker News API 调用
│   ├── logger.py                  # Issue #05: 日志系统
│   └── error_handler.py           # Issue #05: 错误处理
├── tests/
│   ├── __init__.py
│   ├── test_collector.py          # Issue #01: 采集 Agent 测试
│   ├── test_analyzer.py           # Issue #02: 分析 Agent 测试
│   ├── test_organizer.py          # Issue #03: 整理 Agent 测试
│   ├── test_logger.py             # Issue #05: 日志系统测试
│   └── test_error_handler.py      # Issue #05: 错误处理测试
├── .env.example                   # 环境变量示例
├── .gitignore                     # Git 忽略文件
├── AGENTS.md                      # Agent 定义
├── README.md                      # 项目说明
└── requirements.txt               # Python 依赖
```

## 数据流

```
GitHub Trending ─┐
                 ├─→ collector.py → knowledge/raw/YYYY-MM-DD.json
Hacker News ─────┘
                          ↓
                 analyzer.py → knowledge/raw/YYYY-MM-DD.json (带标签)
                          ↓
                 organizer.py → knowledge/articles/{date}-{source}-{slug}.json
```

## 依赖关系

```
collector.py
    ↓
analyzer.py
    ↓
organizer.py
    ↓
daily.yml (GitHub Actions)
```

## 环境变量

| 变量名 | 说明 | 来源 |
|--------|------|------|
| `GITHUB_TOKEN` | GitHub API 认证 | GitHub Secrets |
| `DEEPSEEK_API_KEY` | DeepSeek API 认证 | GitHub Secrets |
