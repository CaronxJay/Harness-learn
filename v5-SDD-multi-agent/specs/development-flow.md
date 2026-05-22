# 开发流程

## 总览

```
Issue #01 (Collector) → Issue #02 (Analyzer) → Issue #03 (Organizer) → Issue #04 (Workflow) → Issue #05 (Error Handling)
```

## 详细流程

### 1. Issue #01: Collector Agent
- **状态**: 已完成
- **依赖**: 无
- **输出**: `knowledge/raw/YYYY-MM-DD.json`
- **任务**:
  - [x] 实现 GitHub Trending 采集
  - [x] 实现 Hacker News 采集
  - [x] 实现 AI 相关过滤
  - [x] 实现数据保存

### 2. Issue #02: Analyzer Agent
- **状态**: 已完成
- **依赖**: Issue #01
- **输入**: `knowledge/raw/YYYY-MM-DD.json`
- **输出**: `knowledge/raw/YYYY-MM-DD.json` (带标签)
- **任务**:
  - [x] 实现数据加载
  - [x] 实现标签生成
  - [x] 实现错误处理
  - [x] 实现单元测试

### 3. Issue #03: Organizer Agent
- **状态**: 已完成
- **依赖**: Issue #01, Issue #02
- **输入**: `knowledge/raw/YYYY-MM-DD.json` (带标签)
- **输出**: `knowledge/articles/{date}-{source}-{slug}.json`
- **任务**:
  - [x] 实现去重检查
  - [x] 实现格式化
  - [x] 实现数据保存
  - [x] 实现单元测试

### 4. Issue #04: GitHub Actions Workflow
- **状态**: 已完成
- **依赖**: Issue #01, Issue #02, Issue #03
- **输出**: `.github/workflows/daily.yml`
- **任务**:
  - [x] 配置定时触发
  - [x] 配置手动触发
  - [x] 配置环境变量
  - [x] 配置错误处理

### 5. Issue #05: 错误处理和日志系统
- **状态**: 已完成
- **依赖**: Issue #01, Issue #02, Issue #03
- **输出**: `src/logger.py`, `src/error_handler.py`
- **任务**:
  - [x] 实现统一日志格式
  - [x] 实现错误分类
  - [x] 实现错误处理策略
  - [x] 实现进度追踪

## 开发顺序

```
Week 1: Issue #01 (Collector Agent)
Week 2: Issue #03 (Organizer Agent)
Week 3: Issue #04 (GitHub Actions Workflow)
Week 4: Issue #05 (错误处理和日志系统)
```

## 验收标准

### Issue #01
- [x] 从 GitHub Trending 采集 Top 20 条项目
- [x] 从 Hacker News 采集 AI 相关热帖
- [x] 过滤 AI 相关内容
- [x] 输出符合 schema v1 的 raw json

### Issue #02
- [x] 输入：符合 schema v1 的 raw json
- [x] 输出：每条数据新增 `tags: {tech, quality, scenario}` 字段
- [x] 失败处理：collector 上游空数据 → 记日志 + skip，不抛异常
- [x] 重跑：幂等（同一输入多次运行结果一致）

### Issue #03
- [x] 读取 knowledge/raw/*.json 中已标注的数据
- [x] 去重检查（按 url 去重）
- [x] 格式化为标准 JSON 格式
- [x] 存储到 knowledge/articles/

### Issue #04
- [x] 每天 UTC 0:00 自动触发
- [x] 支持手动触发
- [x] 串行执行：collector → analyzer → organizer
- [x] 正确配置环境变量

### Issue #05
- [x] 统一日志格式
- [x] 错误分类
- [x] 错误处理策略
- [x] 进度追踪
