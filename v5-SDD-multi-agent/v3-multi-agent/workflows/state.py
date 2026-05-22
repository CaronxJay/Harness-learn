#!/usr/bin/env python3
"""LangGraph 工作流共享状态定义。

报告式通信原则：所有字段承载结构化摘要，而非原始数据。
每个 Agent 上下游通过 TypedDict 字段交接，避免传递冗长的 LLM 原始响应。
"""

from __future__ import annotations

from typing import TypedDict


class KBState(TypedDict):
    """知识库流水线共享状态（LangGraph StateGraph 节点间传递）。

    Attributes:
        plan: Planner 输出的采集策略与关键词配置。
        sources: 采集阶段产出的原始数据摘要列表。
        analyses: LLM 分析后的结构化结果，含摘要/标签/评分。
        articles: 格式化、去重后的最终知识条目。
        review_feedback: 审核节点的反馈意见（非空表示未通过）。
        review_passed: 审核是否通过。
        iteration: 当前审核循环次数（上限 3 次）。
        needs_human_review: HumanFlag 节点设为 True，表示需人工介入。
        cost_tracker: Token 用量与成本追踪汇总。
    """

    # ---- 规划阶段 ----
    plan: dict
    """Planner 输出的采集策略。

    结构:
        {
            "keywords": ["ai agent", "llm framework", ...],
            "sources": ["github_trending", "hacker_news"],
            "max_items": 15,
            "min_relevance": 0.6,
        }
    """

    # ---- 采集阶段 ----
    sources: list[dict]
    """采集到的原始数据摘要列表。

    每个 dict 结构（报告式摘要，非原始响应）:
        {
            "id": "2026-05-07-github-001",
            "source": "github_trending" | "hacker_news",
            "title": "项目/文章标题",
            "url": "原始链接",
            "description": "仓库/文章简介（截断至 300 字符）",
            "metadata": {
                "stars": number | None,
                "hn_points": number | None,
                "language": "en" | "zh",
            },
            "fetched_at": "ISO 8601 时间戳",
        }
    """

    # ---- 分析阶段 ----
    analyses: list[dict]
    """LLM 分析后的结构化结果列表。

    每个 dict 结构:
        {
            "source_id": "2026-05-07-github-001",
            "title": "中文提炼标题",
            "summary": "中文摘要（≤200 字）",
            "summary_en": "英文摘要（原文为英文时填写）",
            "tags": ["agent-framework", "llm", ...],
            "category": "agent-framework" | "llm" | "research" | ...,
            "relevance_score": 0.92,
            "analysis_cost_tokens": 0,
        }
    """

    # ---- 整理与去重阶段 ----
    articles: list[dict]
    """格式化、去重后的最终知识条目列表。

    每个 dict 结构（符合 knowledge/articles/ 下 JSON 规范）:
        {
            "id": "2026-05-07-github-trending-001",
            "title": "...",
            "source": "github_trending" | "hacker_news",
            "source_url": "...",
            "language": "en" | "zh",
            "summary": "...",
            "summary_en": "...",
            "tags": [...],
            "category": "...",
            "relevance_score": 0.0,
            "status": "draft" | "published" | "archived",
            "created_at": "ISO 8601",
            "updated_at": "ISO 8601",
            "metadata": {"stars": n, "hn_points": n, ...},
        }
    """

    # ---- 审核阶段 ----
    review_feedback: str
    """审核节点的反馈意见。

    空字符串表示通过或无反馈；非空表示未通过，需带此反馈重做。
    格式：简洁的结构化建议（≤500 字），例如：
        "准确性不足：第3条摘要将 Apache 2.0 误述为 MIT 协议。请修正。"
    """

    review_passed: bool
    """审核是否通过。True 表示全部条目达标，可以进入发布阶段。"""

    iteration: int
    """当前审核循环次数，0 表示尚未审核，上限 3。"""

    # ---- 人工介入 ----
    needs_human_review: bool
    """是否需要人工介入。由 HumanFlag 节点设为 True，表示自动审核多次未通过。"""

    # ---- 成本追踪 ----
    cost_tracker: dict
    """Token 用量与成本追踪汇总。

    结构:
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
        }
    每个阶段（采集/分析/审核/发布）追加到对应计数器。
    """


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def create_initial_state() -> KBState:
    """创建流水线初始状态，所有集合字段为空，计数器归零。

    Returns:
        KBState: 空白初始状态，供 LangGraph StateGraph 的 entry_point 使用。
    """
    return {
        "plan": {},
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "needs_human_review": False,
        "cost_tracker": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
        },
    }
