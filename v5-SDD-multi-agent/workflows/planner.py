"""Planner Agent — 采集策略规划节点

根据目标采集量选择合适的采集策略（lite/standard/full），
控制数据源数量、相关性阈值和迭代上限。

使用方法：
    from workflows.planner import planner_node, plan_strategy
"""

import logging
import os
from typing import Any

from workflows.state import KBState

logger = logging.getLogger(__name__)


def plan_strategy(target_count: int | None = None) -> dict[str, Any]:
    """根据目标采集量返回采集策略

    三档策略：
    - lite (target < 10):     小规模快速采集，阈值高、迭代少
    - standard (10 <= target < 20): 常规采集，平衡速度与覆盖
    - full (target >= 20):    大规模采集，阈值低、迭代多

    Args:
        target_count: 目标采集量。为 None 时从环境变量
            PLANNER_TARGET_COUNT 读取，默认 10。

    Returns:
        策略 dict，包含 per_source_limit、relevance_threshold、
        max_iterations、target_count、tier、rationale 字段。
    """
    if target_count is None:
        target_count = int(os.getenv("PLANNER_TARGET_COUNT", "10"))

    if target_count < 10:
        tier = "lite"
        strategy = {
            "per_source_limit": 5,
            "relevance_threshold": 0.7,
            "max_iterations": 1,
            "rationale": (
                f"目标量 {target_count} < 10，采用 lite 策略："
                "少量采集即可满足需求，提高相关性阈值(0.7)保证质量，"
                "单轮迭代快速出结果。"
            ),
        }
    elif target_count < 20:
        tier = "standard"
        strategy = {
            "per_source_limit": 10,
            "relevance_threshold": 0.5,
            "max_iterations": 2,
            "rationale": (
                f"目标量 {target_count} 在 10-20 之间，采用 standard 策略："
                "中等采集量，适中的相关性阈值(0.5)平衡覆盖面与质量，"
                "允许 2 轮迭代优化结果。"
            ),
        }
    else:
        tier = "full"
        strategy = {
            "per_source_limit": 20,
            "relevance_threshold": 0.4,
            "max_iterations": 3,
            "rationale": (
                f"目标量 {target_count} >= 20，采用 full 策略："
                "大规模采集保证覆盖面，降低相关性阈值(0.4)纳入更多候选，"
                "最多 3 轮迭代确保质量达标。"
            ),
        }

    strategy["target_count"] = target_count
    strategy["tier"] = tier

    logger.info(
        f"[plan_strategy] target={target_count}, tier={tier}, "
        f"limit={strategy['per_source_limit']}, "
        f"threshold={strategy['relevance_threshold']}, "
        f"iterations={strategy['max_iterations']}"
    )

    return strategy


def planner_node(state: KBState) -> dict:
    """LangGraph 节点包装：生成采集策略并写入 state.plan

    Args:
        state: 当前工作流状态（当前未使用特定字段，预留扩展）

    Returns:
        {"plan": {...}} 部分状态更新
    """
    logger.info("[planner_node] 开始规划采集策略")

    plan = plan_strategy()

    logger.info(f"[planner_node] 策略选定: tier={plan['tier']}")
    return {"plan": plan}
