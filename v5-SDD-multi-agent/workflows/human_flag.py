"""HumanFlag Agent — 人工介入节点（异常终点）

审核循环超过 max_iterations 时的兜底处理。
问题条目写入 knowledge/pending_review/ 目录，不污染主知识库。

使用方法：
    from workflows.human_flag import human_flag_node
"""

import json
import logging
import os
from datetime import datetime, timezone

from workflows.state import KBState

logger = logging.getLogger(__name__)


def human_flag_node(state: KBState) -> dict:
    """审核循环超过上限时的兜底 —— 写入 pending_review/ 目录

    Args:
        state: 当前工作流状态，需要 analyses、iteration、review_feedback 字段

    Returns:
        {"needs_human_review": True} 部分状态更新
    """
    analyses = state.get("analyses", [])
    iteration = state.get("iteration", 0)
    feedback = state.get("review_feedback", "")

    logger.warning(f"[human_flag] 达到 {iteration} 次审核仍未通过")
    logger.info(f"[human_flag] 最后反馈: {feedback[:200]}")

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pending_dir = os.path.join(base, "knowledge", "pending_review")
    os.makedirs(pending_dir, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    filepath = os.path.join(pending_dir, f"pending-{today}.json")

    payload = {
        "timestamp": today,
        "iterations_used": iteration,
        "last_feedback": feedback,
        "analyses": analyses,
    }

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info(f"[human_flag] 已保存到 {filepath}")
    except IOError as e:
        logger.error(f"[human_flag] 写入失败: {e}")

    return {"needs_human_review": True}
