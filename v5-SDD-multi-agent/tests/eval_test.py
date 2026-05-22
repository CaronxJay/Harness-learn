"""AI 知识库评估测试

包含正面/负面/边界案例，以及 LLM-as-Judge 评分测试。

运行方式：
    pytest tests/eval_test.py -v              # 跳过 slow 测试
    pytest tests/eval_test.py -v --runslow    # 包含 slow 测试
"""

import sys
import warnings
from pathlib import Path

import pytest

# 加载 .env，让 pytest 能读到 LLM_API_KEY 等环境变量
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv 未安装时跳过

# 屏蔽自定义 mark 警告
warnings.filterwarnings("ignore", category=pytest.PytestUnknownMarkWarning)

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows.model_client import chat


# ============================================================
# 自定义 mark：--runslow 跳过 slow 测试
# ============================================================


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="运行 slow 测试"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: 需要调用 LLM 的慢速测试")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        return
    skip_slow = pytest.mark.skip(reason="需要 --runslow 选项")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


# ============================================================
# 评估用例定义
# ============================================================

SYSTEM_PROMPT = "你是一个 AI/LLM 领域的技术分析专家。请对输入内容进行分析，输出 JSON 格式：{\"summary\": \"摘要\", \"relevance\": 0-1 分, \"tags\": [\"tag1\"]}"

EVAL_CASES = [
    {
        "name": "正面案例 - 技术文章",
        "input": (
            "LangGraph 是 LangChain 团队开发的有状态 Agent 框架，"
            "支持循环、分支和持久化。核心概念包括 State、Node、Edge，"
            "可用于构建 RAG Pipeline、Multi-Agent 系统等复杂应用。"
        ),
        "expected": {
            "has_summary": True,
            "min_relevance": 0.5,
            "tag_check": lambda tags: isinstance(tags, list) and len(tags) >= 1,
        },
    },
    {
        "name": "负面案例 - 无关内容",
        "input": (
            "今天天气真好，适合出去散步。中午吃了红烧肉，味道不错。"
        ),
        "expected": {
            "has_summary": True,
            "max_relevance": 0.5,
            "tag_check": lambda tags: isinstance(tags, list),
        },
    },
    {
        "name": "边界案例 - 极短输入",
        "input": "AI",
        "expected": {
            "has_summary": True,
            "min_relevance": 0.0,
            "max_relevance": 1.0,
            "tag_check": lambda tags: isinstance(tags, list),
        },
    },
]


# ============================================================
# 本地验证测试（不调用 LLM）
# ============================================================


class TestEvalCasesStructure:
    """验证 EVAL_CASES 结构正确性"""

    def test_cases_not_empty(self):
        assert len(EVAL_CASES) >= 3

    def test_each_case_has_required_fields(self):
        for case in EVAL_CASES:
            assert "name" in case, f"缺少 name: {case}"
            assert "input" in case, f"缺少 input: {case}"
            assert "expected" in case, f"缺少 expected: {case}"

    def test_expected_has_valid_checks(self):
        valid_keys = {"has_summary", "min_relevance", "max_relevance", "tag_check"}
        for case in EVAL_CASES:
            expected = case["expected"]
            assert set(expected.keys()) <= valid_keys, (
                f"{case['name']} 包含未知 key: {set(expected.keys()) - valid_keys}"
            )
            if "min_relevance" in expected:
                assert 0.0 <= expected["min_relevance"] <= 1.0
            if "max_relevance" in expected:
                assert 0.0 <= expected["max_relevance"] <= 1.0

    def test_case_names_unique(self):
        names = [c["name"] for c in EVAL_CASES]
        assert len(names) == len(set(names)), "用例名称不唯一"

    def test_tag_check_is_callable(self):
        for case in EVAL_CASES:
            tc = case["expected"].get("tag_check")
            if tc is not None:
                assert callable(tc), f"{case['name']} 的 tag_check 不可调用"


# ============================================================
# LLM 评估测试（slow）
# ============================================================


def _parse_llm_response(text: str) -> dict:
    """从 LLM 响应中提取 JSON 字段（宽松解析）"""
    import json
    import re

    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 尝试找第一个 { ... }
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


@pytest.mark.slow
@pytest.mark.parametrize("case", EVAL_CASES, ids=[c["name"] for c in EVAL_CASES])
def test_llm_analysis(case):
    """调用 LLM 分析输入，验证结果符合预期"""
    text, usage = chat(case["input"], system=SYSTEM_PROMPT)
    result = _parse_llm_response(text)

    expected = case["expected"]

    # 检查摘要存在
    if expected.get("has_summary"):
        assert "summary" in result, f"缺少 summary 字段，原始响应: {text[:200]}"
        assert len(str(result["summary"])) >= 1, "summary 为空"

    # 检查相关性范围
    relevance = result.get("relevance", -1)
    if "min_relevance" in expected:
        assert relevance >= expected["min_relevance"], (
            f"relevance={relevance} < {expected['min_relevance']}"
        )
    if "max_relevance" in expected:
        assert relevance <= expected["max_relevance"], (
            f"relevance={relevance} > {expected['max_relevance']}"
        )

    # 检查标签
    if "tag_check" in expected:
        tags = result.get("tags", [])
        assert expected["tag_check"](tags), f"tag_check 失败: tags={tags}"


@pytest.mark.slow
def test_llm_as_judge():
    """LLM-as-Judge：让 LLM 对分析结果打分，断言 >= 5"""
    sample_input = (
        "RAG（Retrieval-Augmented Generation）是一种结合检索和生成的 LLM 应用模式，"
        "通过向量数据库检索相关文档，再送入大模型生成回答，提升准确性和可追溯性。"
    )

    # 先获取分析结果
    analysis_text, _ = chat(sample_input, system=SYSTEM_PROMPT)

    # 让 LLM 打分
    judge_prompt = f"""请对以下技术分析结果进行评分（1-10 分）。

分析内容：
{analysis_text}

评分标准：
- 准确性：信息是否正确
- 完整性：是否覆盖关键点
- 可读性：是否清晰易懂

请只输出一个 JSON：{{"score": <1-10>, "reason": "简要理由"}}"""

    score_text, _ = chat(judge_prompt)
    result = _parse_llm_response(score_text)

    score = result.get("score", 0)
    assert isinstance(score, (int, float)), f"score 类型错误: {score_text}"
    assert score >= 5, f"LLM-as-Judge 评分过低: {score}，原因: {result.get('reason', 'N/A')}"
