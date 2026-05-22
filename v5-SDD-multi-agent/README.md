# AI 知识库

自动采集 GitHub Trending 和 Hacker News 的 AI/LLM/Agent 技术动态，经 AI 分析后结构化存储为 JSON。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的 API Key：

```bash
cp .env.example .env
```

需要的环境变量：
- `GITHUB_TOKEN`: GitHub API Token
- `DEEPSEEK_API_KEY`: DeepSeek API Key

### 3. 运行分析

```bash
python src/analyzer.py
```

## 项目结构

```
ai-knowledge-base/
├── .github/workflows/daily.yml   # GitHub Actions workflow
├── .opencode/agents/              # Agent 定义
├── knowledge/
│   ├── raw/                       # 原始采集数据
│   └── articles/                  # 分析后的知识条目
├── logs/                          # 日志文件
├── specs/                         # 项目文档
│   ├── issues.md                  # Issues 列表
│   └── schemas/                   # JSON Schema
├── src/                           # 源代码
├── tests/                         # 测试代码
├── .env.example                   # 环境变量示例
├── .gitignore                     # Git 忽略文件
├── AGENTS.md                      # Agent 定义
├── README.md                      # 本文件
└── requirements.txt               # Python 依赖
```

## Agent 工作流程

```
collector → analyzer → organizer
```

1. **Collector**: 从 GitHub Trending 和 Hacker News 采集技术动态
2. **Analyzer**: 为每条数据打标签（技术方向、质量等级、适用场景）
3. **Organizer**: 去重、格式化、存档到 `knowledge/articles/`

## 输出格式

### Raw (knowledge/raw/)

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

### Analyzed (knowledge/articles/)

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
  "status": "analyzed",
  "collected_at": "2026-03-01T10:00:00Z"
}
```

## 开发

### Issues 列表

详见 [specs/issues.md](specs/issues.md)，包含所有待开发任务和依赖关系。

### 运行测试

```bash
pytest tests/
```

### 代码风格

- 遵循 PEP 8
- 命名：`snake_case`（变量、函数、模块），`PascalCase`（类）
- 文档字符串：Google 风格
- 禁止裸 `print()`，必须使用 `logging` 模块
