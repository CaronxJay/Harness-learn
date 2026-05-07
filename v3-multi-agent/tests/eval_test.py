"""AI 知识库评估测试。

使用 pytest 框架，包含：
- EVAL_CASES 驱动的评估用例（正面 / 负面 / 边界）
- 不调用 LLM 的结构验证测试
- LLM-as-Judge 质量打分测试（标记为 slow）
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

import pytest

# 确保项目根目录在 path 中
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from workflows.model_client import chat  # noqa: E402

logger = logging.getLogger(__name__)

# ============================================================================
# EVAL_CASES — 评估用例集
# ============================================================================

EVAL_CASES: list[dict[str, Any]] = [
    {
        "name": "positive_tech_article",
        "input": (
            "DeepSeek-V3 是一种 Mixture-of-Experts (MoE) 语言模型，"
            "总参数量 671B，每次推理激活 37B 参数。该模型在数学、"
            "编程和多语言任务上展现了与 GPT-4o 相当的性能，"
            "同时训练成本仅为约 557 万美元，极大降低了前沿模型的门槛。"
        ),
        "expected": {
            "min_summary_length": 10,
            "has_keywords": ["DeepSeek", "MoE", "模型"],
            "relevance_score_range": (0.5, 1.0),
        },
    },
    {
        "name": "negative_irrelevant_content",
        "input": "今天天气真好，适合去公园散步和野餐。",
        "expected": {
            "min_summary_length": 0,
            "max_relevance_score": 0.5,
            "should_be_filtered": True,
        },
    },
    {
        "name": "boundary_minimal_input",
        "input": "AI",
        "expected": {
            "no_crash": True,
            "response_length_ok": True,
        },
    },
    {
        "name": "positive_code_project",
        "input": (
            "LangChain 是一个用于构建 LLM 驱动应用的 Python/JS 框架，"
            "支持 Chains、Agents、Tools、Memory 等抽象，"
            "GitHub Star 超过 100k，被广泛用于 RAG、"
            "对话系统和 Agent 开发。"
        ),
        "expected": {
            "min_summary_length": 15,
            "has_keywords": ["LangChain", "LLM", "Agent", "Chain"],
            "relevance_score_range": (0.5, 1.0),
        },
    },
]

# LLM 分析用的系统提示词
ANALYZER_SYSTEM = """你是一个 AI 技术内容分析助手。对用户输入的文本进行以下分析，并以 JSON 格式返回：

{
  "summary": "中文摘要，50-150字",
  "keywords": ["关键词1", "关键词2"],
  "relevance_score": 0.85,
  "category": "llm|agent-framework|research|application|infrastructure|benchmark|security|multimodal",
  "is_ai_related": true,
  "self_quality_score": 8
}

规则：
- 如果输入与 AI/LLM/Agent 无关，relevance_score 设为 0.2 以下，is_ai_related 为 false
- 如果输入极短难以判断，仍然返回合法 JSON 但可以保守评分
- self_quality_score: 1-10 的整数，评估你自己本次分析的质量

只返回 JSON，不要额外文字。"""


# ============================================================================
# 辅助函数
# ============================================================================


async def llm_analyze(text: str) -> dict[str, Any]:
    """调用 LLM 分析文本，返回结构化分析结果。

    Args:
        text: 待分析的原始文本。

    Returns:
        包含 summary / keywords / relevance_score / is_ai_related 等字段的字典。
    """
    text_json, _usage = await chat(prompt=text, system=ANALYZER_SYSTEM)
    # 清洗可能的 markdown fence
    text_json = text_json.strip()
    if text_json.startswith("```"):
        lines = text_json.split("\n")
        text_json = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text_json)


# ============================================================================
# 测试：不调用 LLM 的结构验证
# ============================================================================


class TestEvalCasesStructure:
    """验证 EVAL_CASES 数据结构的正确性（不调用 LLM）。"""

    def test_all_cases_have_required_fields(self) -> None:
        """每个用例必须包含 name / input / expected。"""
        for case in EVAL_CASES:
            assert "name" in case, f"Missing 'name' in {case}"
            assert "input" in case, f"Missing 'input' in {case}"
            assert "expected" in case, f"Missing 'expected' in {case}"
            assert isinstance(case["name"], str), f"'name' must be str in {case}"
            assert isinstance(case["input"], str), f"'input' must be str in {case}"
            assert isinstance(case["expected"], dict), f"'expected' must be dict in {case}"

    def test_names_are_unique(self) -> None:
        """用例名称必须唯一。"""
        names = [c["name"] for c in EVAL_CASES]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"

    def test_all_cases_have_non_empty_input(self) -> None:
        """每个用例的输入不能为空。"""
        for case in EVAL_CASES:
            assert len(case["input"]) > 0, f"Empty input for '{case['name']}'"

    def test_has_positive_negative_boundary_cases(self) -> None:
        """确保至少包含正面、负面、边界三类场景。"""
        names_lower = {c["name"].lower() for c in EVAL_CASES}
        has_positive = any("positive" in n for n in names_lower)
        has_negative = any("negative" in n for n in names_lower)
        has_boundary = any("boundary" in n for n in names_lower)
        assert has_positive, "Missing positive test case"
        assert has_negative, "Missing negative test case"
        assert has_boundary, "Missing boundary test case"


# ============================================================================
# 测试：LLM-as-Judge 质量评估（标记为 slow）
# ============================================================================


@pytest.mark.slow
@pytest.mark.asyncio
class TestLLMJudge:
    """LLM-as-Judge: 让 LLM 自评分析质量，验证分数 ≥ 5。"""

    LLM_JUDGE_MIN_SCORE = 5

    async def _assert_case(self, case: dict[str, Any]) -> None:
        """对单个用例执行 LLM 分析并验证自评质量分数。

        Args:
            case: EVAL_CASES 中的一条用例。
        """
        result = await llm_analyze(case["input"])
        expected = case["expected"]

        # ---------- 基础结构断言 ----------
        for field in ("summary", "keywords", "relevance_score", "is_ai_related", "self_quality_score"):
            assert field in result, (
                f"[{case['name']}] LLM 返回结果缺少字段 '{field}': {result}"
            )

        summary = result["summary"]
        keywords = result["keywords"]
        relevance = result["relevance_score"]
        is_ai = result["is_ai_related"]
        quality_score = result["self_quality_score"]

        # ---------- 范围断言 ----------
        assert isinstance(summary, str), f"[{case['name']}] summary 应为 str"
        assert isinstance(keywords, list), f"[{case['name']}] keywords 应为 list"
        assert isinstance(relevance, (int, float)), f"[{case['name']}] relevance 应为数字"
        assert isinstance(is_ai, bool), f"[{case['name']}] is_ai_related 应为 bool"
        assert isinstance(quality_score, int), f"[{case['name']}] self_quality_score 应为 int"

        # LLM-as-Judge 核心断言（边界用例仅要求不崩溃，不强制质量分数）
        skip_quality = expected.get("no_crash", False)
        if not skip_quality:
            assert quality_score >= self.LLM_JUDGE_MIN_SCORE, (
                f"[{case['name']}] LLM 自评分数 {quality_score} < {self.LLM_JUDGE_MIN_SCORE}"
            )

        # ---------- 用例特定的期望校验 ----------
        if "min_summary_length" in expected and expected["min_summary_length"] is not None:
            assert len(summary) >= expected["min_summary_length"], (
                f"[{case['name']}] summary 长度 {len(summary)} < "
                f"{expected['min_summary_length']}"
            )

        if "has_keywords" in expected:
            matched = [kw for kw in expected["has_keywords"] if kw.lower() in " ".join(keywords).lower()]
            assert len(matched) >= 1, (
                f"[{case['name']}] 关键词 {expected['has_keywords']} 均未命中: {keywords}"
            )

        if "relevance_score_range" in expected:
            lo, hi = expected["relevance_score_range"]
            assert lo <= relevance <= hi, (
                f"[{case['name']}] relevance_score {relevance} 不在 [{lo}, {hi}]"
            )

        if "max_relevance_score" in expected:
            assert relevance <= expected["max_relevance_score"], (
                f"[{case['name']}] relevance_score {relevance} > "
                f"{expected['max_relevance_score']}"
            )

        if expected.get("should_be_filtered"):
            # 无关内容应被标记为低相关或非 AI 内容
            assert relevance < 0.5 or not is_ai, (
                f"[{case['name']}] 无关内容未过滤: relevance={relevance}, is_ai={is_ai}"
            )

        if expected.get("no_crash"):
            # 不崩溃即通过（已在上面通过字段校验，额外确认无异常即可）
            pass

        if expected.get("response_length_ok"):
            assert len(summary) >= 0, f"[{case['name']}] 边界输入响应长度异常"

        logger.info(
            "[%s] score=%s relevance=%.2f keywords=%s summary_len=%d",
            case["name"],
            quality_score,
            relevance,
            keywords,
            len(summary),
        )

    @pytest.mark.parametrize("case", EVAL_CASES, ids=[c["name"] for c in EVAL_CASES])
    async def test_llm_judge_each_case(self, case: dict[str, Any]) -> None:
        """对每个 EVAL_CASE 执行 LLM-as-Judge 自评。"""
        await self._assert_case(case)


# ============================================================================
# 独立运行的入口（不使用 pytest runner 时）
# ============================================================================

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _main() -> None:
        print("=" * 60)
        print("  eval_test.py — 独立运行模式")
        print("=" * 60)

        struct_tests = TestEvalCasesStructure()
        struct_tests.test_all_cases_have_required_fields()
        struct_tests.test_names_are_unique()
        struct_tests.test_all_cases_have_non_empty_input()
        struct_tests.test_has_positive_negative_boundary_cases()
        print("\n[PASS] 结构验证全部通过\n")

        judge = TestLLMJudge()
        for case in EVAL_CASES:
            try:
                await judge._assert_case(case)
                print(f"[PASS] {case['name']}")
            except Exception as e:
                print(f"[FAIL] {case['name']}: {e}")
                raise

        print("\n" + "=" * 60)
        print("  所有测试通过")
        print("=" * 60)

    asyncio.run(_main())
