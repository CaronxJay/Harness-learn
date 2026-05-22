#!/usr/bin/env python3
"""LangGraph 工作流组装 — 知识库采集/分析/整理/审核/保存流水线。

节点图:
    plan → collect → analyze → review ──passed──→ organize → save → END
                                   │    │
                                   │    └─ not passed, iter<3 ──→ revise → review (循环)
                                   │
                                   └─ not passed, iter>=3 → human_flag → END
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Literal

from langgraph.graph import END, StateGraph

from workflows.model_client import BudgetExceededError, get_cost_guard
from workflows.human_flag import human_flag_node
from workflows.nodes import (
    analyze_node,
    collect_node,
    organize_node,
    save_node,
)
from workflows.planner import planner_node
from workflows.reviewer import review_node
from workflows.reviser import revise_node
from workflows.state import KBState, create_initial_state

logger = logging.getLogger(__name__)


def route_after_review(state: KBState) -> Literal["organize", "revise", "human_flag"]:
    """审核后的 3 路条件路由。

    - passed=True → organize（继续整理/保存）
    - passed=False 且 iteration < plan.max_iterations → revise（带反馈修正）
    - passed=False 且 iteration >= plan.max_iterations → human_flag（人工介入）
    """
    passed = state.get("review_passed", False)
    iteration = state.get("iteration", 0)
    plan = state.get("plan", {}) or {}
    max_iter = int(plan.get("max_iterations", 3))

    if passed:
        return "organize"

    if iteration >= max_iter:
        logger.warning("审核 %d 轮仍未通过 → 人工介入", iteration)
        return "human_flag"

    logger.info("审核未通过 (iter=%d) → 进入修正", iteration)
    return "revise"


def build_graph() -> StateGraph:
    """构建并编译 LangGraph 知识库流水线。

    Returns:
        编译后的 StateGraph app，可通过 app.ainvoke(initial_state) 异步执行。
    """
    graph = StateGraph(KBState)

    # 注册节点
    graph.add_node("plan", planner_node)
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("review", review_node)
    graph.add_node("revise", revise_node)
    graph.add_node("organize", organize_node)
    graph.add_node("save", save_node)
    graph.add_node("human_flag", human_flag_node)

    # 线性边
    graph.add_edge("plan", "collect")
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "review")

    # 条件边: review → 3 路分支
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {
            "organize": "organize",
            "revise": "revise",
            "human_flag": "human_flag",
        },
    )

    # 修正后回到审核
    graph.add_edge("revise", "review")

    # 通过后: 整理 → 保存 → 结束
    graph.add_edge("organize", "save")
    graph.add_edge("save", END)

    # 人工介入 → 结束
    graph.add_edge("human_flag", END)

    # 入口
    graph.set_entry_point("plan")

    return graph.compile()


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------


def _print_state_summary(step: str, state: dict | None) -> None:
    """打印每个节点执行后的关键状态摘要。"""
    if state is None:
        print(f"\n{'─' * 50}")
        print(f"  [{step}] (无状态变更)")
        return

    print(f"\n{'─' * 50}")
    print(f"  [{step}]")
    if "plan" in state and state["plan"]:
        p = state["plan"]
        print(f"  plan      : tier={p.get('tier')}, target={p.get('target_count')}")
    if "sources" in state:
        print(f"  sources   : {len(state['sources'])}")
    if "analyses" in state:
        print(f"  analyses  : {len(state['analyses'])}")
    if "articles" in state:
        print(f"  articles  : {len(state['articles'])}")
    if "review_passed" in state:
        print(f"  review    : passed={state['review_passed']}, "
              f"iteration={state.get('iteration')}")
    if state.get("review_feedback"):
        print(f"  feedback  : {state['review_feedback'][:100]}...")
    if state.get("needs_human_review"):
        print(f"  ⚠ human   : 需要人工介入")
    ct = state.get("cost_tracker", {})
    if ct.get("total_tokens", 0) > 0:
        print(f"  tokens    : {ct['total_tokens']} "
              f"(prompt={ct['prompt_tokens']} "
              f"completion={ct['completion_tokens']})")


async def _stream_invoke(app: StateGraph, initial_state: KBState) -> None:
    """流式执行，累积完整状态并逐节点打印。"""
    print("=" * 60)
    print("  LangGraph 知识库流水线 — 流式执行")
    print("=" * 60)

    accumulated: dict = dict(initial_state)
    async for event in app.astream(initial_state):
        for node_name, node_output in event.items():
            _print_state_summary(node_name, node_output)
            if node_output is not None:
                accumulated.update(node_output)

    final_state = accumulated

    print(f"\n{'─' * 50}")
    if final_state:
        ct = final_state.get("cost_tracker", {})
        print(f"  总 tokens: {ct.get('total_tokens', 0)}")
        articles = final_state.get("articles", [])
        if articles:
            print(f"  最终产出: {len(articles)} 条文章")
            for a in articles[:3]:
                print(f"    - {a.get('title', 'N/A')}  "
                      f"(评分: {a.get('relevance_score', 'N/A')})")
    print("=" * 60)
    print("  流水线完成")
    print("=" * 60)


def _run_tests() -> None:
    """运行 LangGraph 流水线测试 + 成本报告收尾。"""
    api_key = os.getenv("API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("未检测到 API_KEY，请设置 DEEPSEEK_API_KEY 后重试。")
        sys.exit(1)

    async def _main() -> None:
        app = build_graph()
        state = create_initial_state()

        try:
            final_state = await app.ainvoke(state)
            print("\n=== 工作流完成 ===")
        except BudgetExceededError as e:
            print(f"\n[FATAL] 预算熔断触发：{e}")

        # ★ 收尾打成本报告 · 落盘到 knowledge/cost_report_{timestamp}.json
        guard = get_cost_guard()
        report = guard.get_report()
        summary = report["summary"]
        print(
            f"\n[CostGuard] 总调用 {summary['total_calls']} 次 · "
            f"总 token P={summary['total_prompt_tokens']} "
            f"C={summary['total_completion_tokens']} · "
            f"总成本 ¥{summary['total_cost_yuan']:.6f}"
        )
        print(
            f"[CostGuard] 按节点：\n"
            f"  {json.dumps(report['by_node'], ensure_ascii=False, indent=2).replace(chr(10), chr(10) + '  ')}"
        )
        path = guard.save_report()
        print(f"[CostGuard] 报告已落盘：{path}")

    asyncio.run(_main())


if __name__ == "__main__":
    _run_tests()
