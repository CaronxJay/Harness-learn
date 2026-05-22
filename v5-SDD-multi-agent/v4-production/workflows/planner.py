#!/usr/bin/env python3
"""Planner 节点 — 根据目标采集量输出执行策略。

三档策略：lite / standard / full，按 target_count 自动选择。
"""

from __future__ import annotations

import os
from typing import Any

from workflows.state import KBState

# ---------------------------------------------------------------------------
# 策略配置
# ---------------------------------------------------------------------------

STRATEGIES: dict[str, dict[str, Any]] = {
    "lite": {
        "per_source_limit": 5,
        "relevance_threshold": 0.7,
        "max_iterations": 1,
        "rationale": (
            "目标采集量 < 10 条，采用精简策略：每数据源仅抓 5 条，"
            "相关度阈值提高到 0.7（过滤噪声），审核最多 1 轮（快速交付）。"
        ),
    },
    "standard": {
        "per_source_limit": 10,
        "relevance_threshold": 0.5,
        "max_iterations": 2,
        "rationale": (
            "目标采集量 10-19 条，采用标准策略：每数据源抓 10 条，"
            "相关度阈值 0.5（平衡覆盖与噪声），审核最多 2 轮。"
        ),
    },
    "full": {
        "per_source_limit": 20,
        "relevance_threshold": 0.4,
        "max_iterations": 3,
        "rationale": (
            "目标采集量 >= 20 条，采用完整策略：每数据源抓 20 条，"
            "相关度阈值降至 0.4（最大化覆盖面），审核最多 3 轮（深度把关）。"
        ),
    },
}

DEFAULT_TARGET = 10


# ---------------------------------------------------------------------------
# plan_strategy
# ---------------------------------------------------------------------------


def plan_strategy(target_count: int | None = None) -> dict[str, Any]:
    """根据目标采集量选择执行策略。

    三档策略：
        lite     (target < 10):  少量采集 + 高相关度阈值 + 1 轮审核
        standard (10-19):        标准采集 + 中等阈值 + 2 轮审核
        full     (>= 20):        大批采集 + 低相关度阈值 + 3 轮审核

    Args:
        target_count: 目标采集条目数。为 None 时从环境变量
                      PLANNER_TARGET_COUNT 读取，默认 10。

    Returns:
        策略 dict，包含 per_source_limit / relevance_threshold /
        max_iterations / tier / rationale 等字段。
    """
    if target_count is None:
        target_count = int(os.getenv("PLANNER_TARGET_COUNT", DEFAULT_TARGET))

    if target_count < 10:
        tier = "lite"
    elif target_count < 20:
        tier = "standard"
    else:
        tier = "full"

    strategy = dict(STRATEGIES[tier])
    strategy["tier"] = tier
    strategy["target_count"] = target_count

    return strategy


# ---------------------------------------------------------------------------
# planner_node
# ---------------------------------------------------------------------------


def planner_node(state: KBState) -> dict[str, Any]:
    """LangGraph 节点：读取规划参数，生成执行策略写入 state.plan。

    Args:
        state: KBState 共享状态。

    Returns:
        {"plan": strategy_dict}
    """
    plan = plan_strategy()
    print(
        f"[Planner] 档位={plan['tier']} | "
        f"目标={plan['target_count']}条 | "
        f"每源上限={plan['per_source_limit']} | "
        f"相关度阈值={plan['relevance_threshold']} | "
        f"最多迭代={plan['max_iterations']}次"
    )
    print(f"[Planner] {plan['rationale']}")
    return {"plan": plan}


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------


def _run_tests() -> None:
    """运行策略选择测试。"""
    print("=" * 60)
    print("  workflows/planner.py — 策略选择测试")
    print("=" * 60)

    test_targets = [5, 10, 15, 20, 30, None]
    for tc in test_targets:
        plan = plan_strategy(tc)
        label = f"target={tc}" if tc is not None else "default (env)"
        print(
            f"\n  [{label}] → tier={plan['tier']} "
            f"limit={plan['per_source_limit']} "
            f"min_rel={plan['relevance_threshold']} "
            f"max_iter={plan['max_iterations']}"
        )
        print(f"    {plan['rationale'][:80]}...")

    # Test planner_node
    print(f"\n  --- planner_node 测试 ---")
    from workflows.state import create_initial_state
    state = create_initial_state()
    result = planner_node(state)
    print(f"  返回 plan.tier = {result['plan']['tier']}")

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)


if __name__ == "__main__":
    _run_tests()
