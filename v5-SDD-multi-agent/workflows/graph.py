"""LangGraph 工作流图定义

构建 collect → analyze → organize → review → save 工作流。
review 不通过时进入 revise 节点修改，再循环回 review（最多 3 次迭代）。
超过上限时进入 human_flag 节点（异常终点）。

使用方法：
    from workflows.graph import build_graph

    graph = build_graph()
    result = graph.invoke(initial_state)
"""

import logging

from langgraph.graph import END, StateGraph

from workflows.human_flag import human_flag_node
from workflows.nodes import (
    analyze_node,
    collect_node,
    organize_node,
    review_node,
    save_node,
)
from workflows.reviser import revise_node
from workflows.state import KBState

logger = logging.getLogger(__name__)

MAX_REVIEW_ITERATIONS = 3


def route_after_review(state: KBState) -> str:
    """审核后的 3 路路由

    Args:
        state: 当前工作流状态

    Returns:
        下一个节点名称
    """
    if state.get("review_passed", False):
        return "organize"
    if state.get("iteration", 0) >= MAX_REVIEW_ITERATIONS:
        return "human_flag"
    return "revise"


def build_graph() -> StateGraph:
    """构建并编译工作流图

    流程：
        collect → analyze → organize → review
                ↑                   │
                └───────────────────┘
                                        ├─ (通过) → organize → save → END
                                        ├─ (不通过, iteration < 3) → revise → review（循环）
                                        └─ (不通过, iteration >= 3) → human_flag → END

    Returns:
        编译后的 LangGraph 图
    """
    workflow = StateGraph(KBState)

    # 注册节点
    workflow.add_node("collect", collect_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("organize", organize_node)
    workflow.add_node("review", review_node)
    workflow.add_node("revise", revise_node)
    workflow.add_node("save", save_node)
    workflow.add_node("human_flag", human_flag_node)

    # 定义边
    workflow.set_entry_point("collect")
    workflow.add_edge("collect", "analyze")
    workflow.add_edge("analyze", "organize")
    workflow.add_edge("organize", "review")

    # 条件分支：审核后 3 路路由
    workflow.add_conditional_edges(
        "review",
        route_after_review,
        {
            "organize": "organize",
            "revise": "revise",
            "human_flag": "human_flag",
        },
    )

    # revise 循环回 review
    workflow.add_edge("revise", "review")

    workflow.add_edge("save", END)
    workflow.add_edge("human_flag", END)

    return workflow.compile()


# ============================================================
# 直接运行：执行工作流 + 成本报告
# ============================================================

if __name__ == "__main__":
    from workflows.model_client import get_cost_guard, BudgetExceededError

    app = build_graph()

    initial_state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "needs_human_review": False,
        "plan": {},
        "cost_tracker": {},
    }

    try:
        final_state = app.invoke(initial_state)
        print("\n=== 工作流完成 ===")
    except BudgetExceededError as e:
        print(f"\n[FATAL] 预算熔断触发：{e}")

    # 收尾：打印成本报告并落盘
    guard = get_cost_guard()
    report = guard.get_report()
    summary = report["summary"]
    print(f"\n[CostGuard] 总调用 {summary['total_calls']} 次 · 总成本 ¥{summary['total_cost_yuan']:.4f}")
    print(f"[CostGuard] 按节点：{report['by_node']}")
    guard.save_report("knowledge/cost-report.json")
