#!/usr/bin/env python3
"""Revise 节点 — 根据审核反馈批量修改 analyses。

不替代 organize_node 的过滤/去重/格式化职责，只做内容修正。
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
# Prompt
# ---------------------------------------------------------------------------

REVISE_SYSTEM = (
    "You are a careful editor. Revise a batch of AI repository analysis "
    "entries based on review feedback. Preserve all JSON fields EXCEPT the "
    "ones the feedback asks you to fix. Return valid JSON only."
)

REVISE_PROMPT = (
    "The following AI repository analyses received this review feedback:\n"
    '---FEEDBACK---\n{feedback}\n---END FEEDBACK---\n\n'
    "Please revise each analysis entry to address the feedback. "
    "For entries that do NOT need changes, return them as-is.\n"
    "Preserve all original fields (source_id, title, summary, summary_en, "
    "tags, category, relevance_score) — only modify the content that the "
    "feedback points out.\n\n"
    "Original analyses:\n{analyses}\n\n"
    'Return JSON:\n{{"analyses": [{{"source_id": "...", "title": "...", '
    '"summary": "...", "summary_en": "...", "tags": [...], '
    '"category": "...", "relevance_score": 0.0}}, ...]}}'
)


# ---------------------------------------------------------------------------
# revise_node
# ---------------------------------------------------------------------------


async def revise_node(state: KBState) -> dict[str, Any]:
    """根据审核反馈批量修改 analyses。

    读 state["analyses"] 和 state["review_feedback"]，将 feedback 注入
    prompt 后调 LLM 返回修改后的 analyses 列表。

    - temperature=0.4（允许 LLM 创造性改写）
    - analyses 或 feedback 为空时跳过，返回 {}
    - 保留所有原始字段，只修改反馈指出的问题

    Args:
        state: KBState 共享状态。

    Returns:
        {"analyses": improved, "cost_tracker": tracker} 或 {} (跳过时)。
    """
    print("[ReviseNode] 开始批量修正 analyses...")

    analyses = state.get("analyses", [])
    feedback = state.get("review_feedback", "")

    if not analyses:
        print("[ReviseNode] analyses 为空，跳过")
        return {}
    if not feedback:
        print("[ReviseNode] review_feedback 为空，跳过")
        return {}

    tracker = deepcopy(state.get("cost_tracker", {}))
    analyses_json = json.dumps(analyses, ensure_ascii=False, indent=2)

    # ---------- LLM 批量修正 ----------
    try:
        result, usage = await chat_json(
            REVISE_PROMPT.format(feedback=feedback, analyses=analyses_json),
            system=REVISE_SYSTEM,
            temperature=0.4,
            node_name="revise",
        )
        accumulate_usage(tracker, usage)
    except BudgetExceededError:
        raise
    except Exception as exc:
        logger.warning("[ReviseNode] LLM 修正失败: %s，保留原文", exc)
        return {"cost_tracker": tracker}

    improved = result.get("analyses", [])

    # ---------- 完整性校验 ----------
    if not isinstance(improved, list) or not improved:
        logger.warning("[ReviseNode] LLM 返回了空的 analyses，保留原文")
        return {"cost_tracker": tracker}

    # 对齐 source_id：用原文 ID 补回 LLM 可能遗漏的条目
    original_ids = {a.get("source_id") for a in analyses}
    for item in improved:
        if "source_id" not in item:
            logger.warning("[ReviseNode] LLM 返回条目缺少 source_id，丢弃")
            improved.remove(item)

    # 确保没有丢失原文中的条目
    improved_ids = {a.get("source_id") for a in improved}
    missing = original_ids - improved_ids
    if missing:
        logger.warning(
            "[ReviseNode] LLM 遗漏 %d 条，从原文补回: %s",
            len(missing),
            ", ".join(sorted(missing)),
        )
        for a in analyses:
            if a.get("source_id") in missing:
                improved.append(a)

    print(
        f"[ReviseNode] 修正完成: {len(analyses)} → {len(improved)} 条\n"
        f"  feedback: {feedback[:100]}..."
    )

    return {"analyses": improved, "cost_tracker": tracker}
