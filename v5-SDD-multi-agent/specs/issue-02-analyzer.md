# Issue #02 · Analyzer Agent

## Depends on
- Issue #01 · Collector Agent（必须先产出 knowledge/raw/*.json）

## Description
读取 knowledge/raw/*.json，为每条数据打 3 维度标签（技术方向 / 质量等级 / 适用场景）。

## Acceptance Criteria
- [x] 输入：符合 schema v1 的 raw json（见 specs/schemas/raw.json）
- [x] 输出：每条数据新增 `tags: {tech, quality, scenario}` 字段
- [x] 失败处理：collector 上游空数据 → 记日志 + skip，不抛异常
- [x] 重跑：幂等（同一输入多次运行结果一致）

## 实现细节

### 文件结构
- `src/analyzer.py`: 分析 Agent 主模块
- `specs/schemas/raw.json`: Raw JSON Schema 定义
- `tests/test_analyzer.py`: 单元测试

### 核心功能
1. **load_raw_data**: 加载原始数据文件，处理各种异常情况
2. **analyze_entry**: 分析单条数据，调用 DeepSeek API 生成标签
3. **analyze_raw_data**: 批量分析原始数据并保存结果

### 三个维度标签
1. **技术方向 (tech_direction)**: llm / agent / rag / multimodal / code-gen / fine-tuning / inference / training / dataset / tool / framework / application
2. **质量等级 (quality_level)**: S(9-10) / A(7-8) / B(5-6) / C(1-4)
3. **适用场景 (use_case)**: 一句话描述谁会用、怎么用

### 错误处理
- 文件不存在：记录日志，返回空数组
- JSON 解析错误：记录日志，返回空数组
- 数据格式错误：记录日志，返回空数组
- API 调用失败：记录日志，返回默认值

### 测试覆盖
- ✅ 加载有效数据
- ✅ 加载空文件
- ✅ 加载无效 JSON
- ✅ 加载非数组 JSON
- ✅ 加载不存在的文件

## 使用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 运行分析
python3 src/analyzer.py

# 运行测试
python3 -m pytest tests/ -v
```
