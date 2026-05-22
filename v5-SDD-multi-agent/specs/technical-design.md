# AI 知识库 · 技术方案 v0.1

## 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.12 |
| AI 平台 | OpenCode + DeepSeek |
| Agent 框架 | LangGraph |
| 工具调用 | OpenClaw |
| 依赖管理 | pip + requirements.txt |
| 运行环境 | GitHub Actions workflow（定时任务） |

## 系统架构

```
GitHub Actions (cron)
    ├── 1. 采集 Agent
    │   ├── GitHub Search API（需 Token）
    │   └── Hacker News API
    ├── 2. 分析 Agent
    │   └── DeepSeek API（需 API Key）
    ├── 3. 整理 Agent
    │   └── 格式化 + 多渠道分发（QQBot、飞书）
    └── 4. 输出结果
        ├── knowledge/raw/       # 原始采集数据
        └── knowledge/articles/  # 分析后的知识条目
```

## 模块划分

### 1. 采集 Agent `fetcher.py`
- 调用 GitHub Search API
- 查询条件：按 stars 排序，最近 24 小时创建或更新
- 返回 Top 20 条
- 采集 Hacker News AI 相关热帖

### 2. 分析 Agent `analyzer.py`
- 调用 DeepSeek API（兼容 OpenAI API 格式）
- 输入：项目 README + 基本信息
- 输出：定位、技术栈、亮点、适用场景、趋势分类
- 添加三个维度标签：
  - **技术方向**：`llm` / `agent` / `rag` / `multimodal` / `code-gen` / `fine-tuning` / `inference` / `training` / `dataset` / `tool` / `framework` / `application`
  - **质量等级**：`S`(9-10) / `A`(7-8) / `B`(5-6) / `C`(1-4)
  - **适用场景**：一句话描述谁会用、怎么用

### 3. 整理 Agent `publisher.py`
- 格式化为标准 JSON
- 分发到 QQBot、飞书等渠道

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

## 环境变量（GitHub Secrets）

| 变量名 | 说明 |
|--------|------|
| `GITHUB_TOKEN` | GitHub API 认证 |
| `DEEPSEEK_API_KEY` | DeepSeek API 认证 |

## 依赖清单 `requirements.txt`

```
requests>=2.31.0
openai>=1.0.0
```

## Workflow 配置 `.github/workflows/daily.yml`

- 触发：每天 UTC 00:00（北京时间 08:00）
- 步骤：checkout → 安装依赖 → 运行脚本 → commit 结果

## 目录结构

```
/
├── .github/workflows/daily.yml
├── .opencode/
│   ├── agents/          # Agent 定义
│   └── skills/          # Skill 定义
├── knowledge/
│   ├── raw/             # 原始采集数据
│   └── articles/        # 分析后的知识条目
├── src/
│   ├── main.py
│   ├── fetcher.py
│   ├── analyzer.py
│   └── publisher.py
├── specs/
│   ├── project-vision.md
│   └── technical-design.md
├── AGENTS.md
└── requirements.txt
```
