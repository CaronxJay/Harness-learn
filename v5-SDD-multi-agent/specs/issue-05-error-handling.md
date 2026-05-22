# Issue #05 · 错误处理和日志系统

## Depends on
- Issue #01 · Collector Agent
- Issue #02 · Analyzer Agent
- Issue #03 · Organizer Agent

## Description
实现统一的错误处理和日志系统，确保任何 Agent 失败时都能记录错误并优雅降级。

## Acceptance Criteria
- [x] 统一日志格式：时间戳、Agent 名称、日志级别、消息
- [x] 错误分类：API 调用失败、数据格式错误、文件操作失败
- [x] 错误处理策略：记日志 + skip，不抛异常
- [x] 日志输出：控制台 + 文件（logs/{date}.log）
- [x] 进度追踪：每个 Agent 的开始/结束时间、成功/失败条数
- [x] 重跑支持：幂等（同一输入多次运行结果一致）

## 实现细节

### 文件结构
- `src/logger.py`: 日志系统模块
- `src/error_handler.py`: 错误处理模块
- `logs/`: 日志文件目录

### 日志格式
```
2026-05-21T08:00:00Z [collector] INFO: 开始采集 GitHub Trending
2026-05-21T08:00:05Z [collector] INFO: 成功采集 20 条数据
2026-05-21T08:00:06Z [collector] ERROR: API 调用失败: 403 Forbidden
```

### 错误分类
1. **API 调用失败**
   - 网络超时
   - 认证失败
   - Rate limit

2. **数据格式错误**
   - JSON 解析失败
   - 字段缺失
   - 类型错误

3. **文件操作失败**
   - 文件不存在
   - 权限不足
   - 磁盘空间不足

### 错误处理策略
- **collector 失败**: 终止流程，记录错误
- **analyzer 失败**: 跳过该条，继续处理其他
- **organizer 失败**: 重试一次，仍失败则记录错误

### 进度追踪
```json
{
  "agent": "collector",
  "start_time": "2026-05-21T08:00:00Z",
  "end_time": "2026-05-21T08:00:10Z",
  "success_count": 20,
  "fail_count": 0,
  "errors": []
}
```

### 测试覆盖
- [x] 测试日志格式
- [x] 测试错误分类
- [x] 测试错误处理策略
- [x] 测试进度追踪

## 使用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试
python3 -m pytest tests/test_logger.py tests/test_error_handler.py -v
```
