#!/usr/bin/env python3
"""Reviewer 节点 — 对 analyses 做加权多维度评分审核。

审核对象是 state["analyses"]（raw LLM 分析结果），而非 state["articles"]。
每维 1-10 分，加权总分 >= 7.0 为通过。
LLM 调用失败时自动通过，不阻塞流程。
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

from workflows.model_client import BudgetExceededError, accumulate_usage, chat_json
from workflows.state import KBState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 权重配置
# ---------------------------------------------------------------------------

WEIGHTS: dict[str, float] = {
    "summary_quality": 0.25,   # 摘要质量：是否准确、简洁、抓住核心
    "technical_depth": 0.25,   # 技术深度：分析是否深入、有洞察
    "relevance": 0.20,         # 相关性：与 AI/LLM/Agent 领域相关度
    "originality": 0.15,       # 原创性：视角是否新颖、有独到见解
    "formatting": 0.15,        # 格式规范：JSON 结构、标签、分类是否规范
}

PASS_THRESHOLD = 7.0
MAX_REVIEW_ITEMS = 5  # 只审前 N 条，控 token

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

REVIEWER_SYSTEM = (
    "You are a strict quality auditor for AI knowledge analysis results. "
    "Evaluate each analysis item on five dimensions (each 1-10). "
    "Be honest and precise — do not inflate scores. "
    "Return valid JSON only."
)

REVIEWER_PROMPT = (
    "Evaluate the following AI repository analyses on five dimensions "
    "(each 1-10):\n"
    "  summary_quality   (25%): 摘要是否准确、简洁、抓住核心\n"
    "  technical_depth   (25%): 技术分析是否深入、有洞察\n"
    "  relevance         (20%): 与 AI/LLM/Agent 领域相关性\n"
    "  originality       (15%): 分析视角是否新颖、有独到见解\n"
    "  formatting        (15%): JSON 结构、标签、分类是否规范\n\n"
    "Analyses:\n{analyses}\n\n"
    'Return JSON:\n'
    '{{"passed": true/false, "overall_score": 7.5, "feedback": "...", '
    '"scores": {{"summary_quality": 8, "technical_depth": 7, '
    '"relevance": 8, "originality": 6, "formatting": 9}}}}'
)


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------

def _compute_weighted_total(scores: dict[str, int]) -> float:
    """用代码重算加权总分，不信任 LLM 的算术结果。

    Args:
        scores: 各维度原始评分 {dim_name: 1-10}。

    Returns:
        加权总分，保留 1 位小数。
    """
    total = sum(scores.get(dim, 0) * weight for dim, weight in WEIGHTS.items())
    return round(total, 1)


async def review_node(state: KBState) -> dict[str, Any]:
    """对 state["analyses"] 做多维度加权评分审核。

    - 只审核前 MAX_REVIEW_ITEMS 条 analyses（控 token）
    - 5 维度加权评分，代码重算总分
    - 加权总分 >= 7.0 为通过
    - iteration >= plan max_iterations 时强制通过（跳过 LLM 调用）
    - LLM 调用异常时自动通过（不阻塞流程）

    Args:
        state: KBState 共享状态。

    Returns:
        部分状态更新 dict：
            review_passed: bool
            review_feedback: str
            iteration: int
            cost_tracker: dict
    """
    print("[ReviewerNode] 开始审核 analyses...")

    plan = state.get("plan", {}) or {}
    max_iterations = int(plan.get("max_iterations", 3))
    iteration = state.get("iteration", 0)

    # 兜底：iteration >= max_iterations 强制通过
    if iteration >= max_iterations:
        print(f"[ReviewerNode] iteration={iteration} >= {max_iterations}，强制通过")
        return {
            "review_feedback": "",
            "review_passed": True,
            "iteration": iteration,
        }

    analyses = state.get("analyses", [])
    if not analyses:
        print("[ReviewerNode] 无 analyses 待审核，视为通过")
        return {"review_feedback": "", "review_passed": True, "iteration": iteration}

    # 只审前 N 条
    sample = analyses[:MAX_REVIEW_ITEMS]
    if len(analyses) > MAX_REVIEW_ITEMS:
        print(
            f"[ReviewerNode] 仅审核前 {MAX_REVIEW_ITEMS}/{len(analyses)} 条 "
            f"（控 token）"
        )

    tracker = deepcopy(state.get("cost_tracker", {}))
    analyses_json = json.dumps(sample, ensure_ascii=False, indent=2)

    # ---------- LLM 调用 ----------
    try:
        result, usage = await chat_json(
            REVIEWER_PROMPT.format(analyses=analyses_json),
            system=REVIEWER_SYSTEM,
            temperature=0.1,
            node_name="review",
        )
        accumulate_usage(tracker, usage)
    except BudgetExceededError:
        raise
    except Exception as exc:
        logger.warning("[ReviewerNode] LLM 审核异常: %s，自动通过", exc)
        return {
            "review_feedback": f"LLM 审核异常: {exc}",
            "review_passed": True,
            "iteration": iteration,
            "cost_tracker": tracker,
        }

    # ---------- 代码重算加权总分 ----------
    llm_scores: dict[str, int] = {
        dim: int(result.get("scores", {}).get(dim, 0))
        for dim in WEIGHTS
    }
    weighted_total = _compute_weighted_total(llm_scores)

    # 用代码结果覆盖 LLM 的 passed / overall_score
    passed = weighted_total >= PASS_THRESHOLD

    feedback = str(result.get("feedback", ""))
    if not passed and not feedback:
        feedback = (
            f"加权总分 {weighted_total:.1f} < {PASS_THRESHOLD}，需改进"
        )

    print(
        f"[ReviewerNode] 审核完成: passed={passed} "
        f"weighted={weighted_total:.1f} (阈={PASS_THRESHOLD}) | "
        f"summary={llm_scores['summary_quality']} "
        f"depth={llm_scores['technical_depth']} "
        f"rel={llm_scores['relevance']} "
        f"orig={llm_scores['originality']} "
        f"fmt={llm_scores['formatting']}"
    )

    # ---------- 构建返回 ----------
    next_iteration = iteration
    if not passed:
        next_iteration = iteration + 1

    return {
        "review_feedback": feedback,
        "review_passed": passed,
        "iteration": next_iteration,
        "cost_tracker": tracker,
    }


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------


def _run_tests() -> None:
    """独立测试 review_node 的评分逻辑。"""
    import os

    print("=" * 60)
    print("  workflows/reviewer.py — Reviewer 加权评分测试")
    print("=" * 60)

    # Test 1: 加权总分计算（无 LLM）
    print("\n[1] 加权总分代码计算测试")
    test_scores = {
        "summary_quality": 8,
        "technical_depth": 7,
        "relevance": 9,
        "originality": 5,
        "formatting": 8,
    }
    total = _compute_weighted_total(test_scores)
    print(f"    输入: {test_scores}")
    print(f"    权重: {WEIGHTS}")
    print(
        f"    手算: 8×0.25 + 7×0.25 + 9×0.20 + 5×0.15 + 8×0.15 = "
        f"2.0 + 1.75 + 1.8 + 0.75 + 1.2 = {2.0+1.75+1.8+0.75+1.2:.1f}"
    )
    print(f"    代码: {total}")
    print(f"    通过: {total >= PASS_THRESHOLD} (阈={PASS_THRESHOLD})")

    # Test 2: Live LLM call (requires API key)
    api_key = os.getenv("API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("\n  未检测到 API_KEY，跳过实时审核测试。")
        return

    print(f"\n[2] 实时审核测试 (provider: {os.getenv('LLM_PROVIDER', 'deepseek')})")

    import asyncio

    async def _live() -> None:
        from workflows.state import create_initial_state

        # 构造假的 analyses
        state = create_initial_state()
        state["analyses"] = [
            {
                "source_id": "2026-05-07-gh-001",
                "title": "LangChain：Agent 工程化平台",
                "summary": "LangChain 是构建 LLM 应用的主流框架...",
                "summary_en": "LangChain is a leading framework for LLM apps...",
                "tags": ["langchain", "llm", "agent", "framework"],
                "category": "agent-framework",
                "relevance_score": 0.95,
            },
            {
                "source_id": "2026-05-07-gh-002",
                "title": "MetaGPT：多智能体元编程框架",
                "summary": "MetaGPT 将软件工程 SOP 编码为 Agent 角色...",
                "summary_en": "MetaGPT encodes software engineering SOPs...",
                "tags": ["multi-agent", "llm", "framework"],
                "category": "agent-framework",
                "relevance_score": 0.92,
            },
        ]

        result = await review_node(state)
        print(f"    结果: passed={result['review_passed']}")
        print(f"    feedback: {result.get('review_feedback', '')[:120]}")
        print(f"    iteration: {result['iteration']}")
        ct = result.get("cost_tracker", {})
        if ct.get("total_tokens", 0):
            print(f"    tokens: {ct['total_tokens']}")

    asyncio.run(_live())

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)


if __name__ == "__main__":
    _run_tests()
