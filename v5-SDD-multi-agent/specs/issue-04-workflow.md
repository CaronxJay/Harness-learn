# Issue #04 · GitHub Actions Workflow

## Depends on
- Issue #01 · Collector Agent
- Issue #02 · Analyzer Agent
- Issue #03 · Organizer Agent

## Description
配置 GitHub Actions workflow，每天 UTC 0:00 触发，串行执行三个 Agent：collector → analyzer → organizer。

## Acceptance Criteria
- [x] 创建 `.github/workflows/daily.yml` 文件
- [x] 每天 UTC 0:00 自动触发（北京时间 08:00）
- [x] 支持手动触发（workflow_dispatch）
- [x] 串行执行：collector → analyzer → organizer
- [x] 正确配置环境变量（GITHUB_TOKEN, DEEPSEEK_API_KEY）
- [x] 失败处理：任何一个 Agent 失败，记录错误并终止流程
- [x] 日志记录：每个 Agent 的开始/结束时间、成功/失败条数

## 实现细节

### 文件结构
- `.github/workflows/daily.yml`: GitHub Actions workflow 配置

### Workflow 配置
```yaml
name: Daily AI Knowledge Collection

on:
  schedule:
    - cron: '0 0 * * *'  # UTC 0:00 = 北京时间 08:00
  workflow_dispatch:  # 支持手动触发

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run Collector
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python3 src/collector.py

  analyze:
    needs: collect
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run Analyzer
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
        run: python3 src/analyzer.py

  organize:
    needs: analyze
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run Organizer
        run: python3 src/organizer.py

  commit:
    needs: organize
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Commit results
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add knowledge/
          git diff --staged --quiet || git commit -m "Update knowledge base $(date +%Y-%m-%d)"
          git push
```

### 环境变量
| 变量名 | 说明 | 来源 |
|--------|------|------|
| `GITHUB_TOKEN` | GitHub API 认证 | GitHub Secrets |
| `DEEPSEEK_API_KEY` | DeepSeek API 认证 | GitHub Secrets |

### 日志记录
- 每个 Agent 的开始/结束时间
- 成功/失败条数
- 错误详情

### 错误处理
- Agent 失败：记录错误，终止流程
- 重试策略：不自动重试，支持手动触发重跑

## 使用方法

### 1. 配置 GitHub Secrets
在仓库设置中添加以下 Secrets：
- `GITHUB_TOKEN`: GitHub API Token
- `DEEPSEEK_API_KEY`: DeepSeek API Key

### 2. 手动触发
在 GitHub Actions 页面，点击 "Run workflow" 按钮

### 3. 查看日志
在 GitHub Actions 页面，查看每个 job 的日志输出
