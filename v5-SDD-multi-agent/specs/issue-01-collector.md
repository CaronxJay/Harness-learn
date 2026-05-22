# Issue #01 · Collector Agent

## Depends on
- None（无依赖，可立即开始）

## Description
从 GitHub Trending 和 Hacker News 采集 AI/LLM/Agent 领域的技术动态，共 20 条，输出到 knowledge/raw/。

## Acceptance Criteria
- [x] 从 GitHub Trending 采集 Top 20 条项目
- [x] 从 Hacker News 采集 AI 相关热帖
- [x] 过滤 AI 相关内容（关键词匹配）
- [x] 输出符合 schema v1 的 raw json（见 specs/schemas/raw.json）
- [x] 存储到 knowledge/raw/{date}.json
- [x] 失败处理：API 调用失败 → 记日志 + skip，不抛异常
- [x] 重跑：幂等（同一输入多次运行结果一致）

## 实现细节

### 文件结构
- `src/collector.py`: 采集 Agent 主模块
- `src/github.py`: GitHub Trending 采集模块
- `src/hackernews.py`: Hacker News 采集模块
- `tests/test_collector.py`: 单元测试

### 核心功能
1. **fetch_github_trending**: 从 GitHub Trending 采集项目
   - 调用 GitHub Search API
   - 按 stars 排序，最近 24 小时创建或更新
   - 返回 Top 20 条

2. **fetch_hackernews**: 从 Hacker News 采集热帖
   - 调用 Hacker News API
   - 筛选 AI 相关帖子
   - 按 points 排序

3. **filter_ai_related**: 过滤 AI 相关内容
   - 关键词匹配：`llm`, `ai`, `machine-learning`, `transformer`, `diffusion`, `neural`, `deep-learning`, `nlp`, `computer-vision`, `agent`, `rag`
   - topic 标签匹配
   - 任一命中即保留

4. **save_raw_data**: 保存原始数据
   - 存储路径：`knowledge/raw/{date}.json`
   - JSON 格式，UTF-8 编码

### 输出格式
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

### 错误处理
- API 调用失败：记录日志，跳过该条
- 网络超时：重试 3 次，仍失败则跳过
- 数据格式错误：记录日志，跳过该条

### 测试覆盖
- [x] 测试 GitHub API 调用
- [x] 测试 Hacker News API 调用
- [x] 测试 AI 相关过滤
- [x] 测试数据保存
- [x] 测试错误处理

## 使用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 GITHUB_TOKEN

# 运行采集
python3 src/collector.py

# 运行测试
python3 -m pytest tests/test_collector.py -v
```
