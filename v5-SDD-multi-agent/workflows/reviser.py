"""LangGraph 工作流修改节点

根据审核反馈修改 analyses 列表。

使用方法：
    from workflows.reviser import revise_node
"""

import json
import logging
from typing import Any

from workflows.model_client import accumulate_usage, chat_json
from workflows.state import KBState

logger = logging.getLogger(__name__)

REVISE_SYSTEM_PROMPT = """你是一个技术内容编辑。
请根据审核反馈，对以下知识分析结果进行批量修改。

原始分析结果：
{analyses}

审核反馈：
{feedback}

要求：
1. 保留每个条目的核心信息（title、source_url、source_type）
2. 根据反馈针对性修改（summary、tags、tech_direction、quality_score 等）
3. 输出修改后的完整 JSON 数组（保持原格式）
4. 确保每个条目都包含必要字段

输出格式：
{{
    "analyses": [
        {{
            "title": "...",
            "summary": "...",
            "tags": ["..."],
            "tech_direction": "...",
            "quality_score": 0.85,
            "use_case": "...",
            "source_url": "...",
            "source_type": "..."
        }}
    ]
}}

只输出 JSON，不要有其他内容。"""


def revise_node(state: KBState) -> dict:
    """根据审核反馈修改 analyses

    Args:
        state: 当前工作流状态，需要 analyses、review_feedback、cost_tracker 字段

    Returns:
        {"analyses": improved, "cost_tracker": tracker} 或 {}（跳过时）
    """
    analyses = state.get("analyses", [])
    feedback = state.get("review_feedback", "")
    cost_tracker = state.get("cost_tracker", {})

    # analyses 或 feedback 空时跳过
    if not analyses or not feedback:
        logger.info("[revise_node] 无内容或无反馈，跳过修改")
        return {}

    logger.info(f"[revise_node] 开始修改 {len(analyses)} 条分析结果")

    # 构建 prompt
    analyses_text = json.dumps(analyses, ensure_ascii=False, indent=2)
    prompt = REVISE_SYSTEM_PROMPT.format(
        analyses=analyses_text,
        feedback=feedback,
    )

    try:
        result, usage = chat_json(prompt, temperature=0.4, node_name="revise")
        accumulate_usage(cost_tracker, usage)

        improved = result.get("analyses", [])

        # 保留原始元数据
        for i, item in enumerate(improved):
            if i < len(analyses):
                item["source_url"] = item.get("source_url", analyses[i].get("source_url", ""))
                item["source_type"] = item.get("source_type", analyses[i].get("source_type", ""))

        logger.info(f"[revise_node] 修改完成，返回 {len(improved)} 条结果")
        return {"analyses": improved, "cost_tracker": cost_tracker}

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"[revise_node] 修改失败: {e}，保留原文")
        return {}
