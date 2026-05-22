#!/usr/bin/env python3
"""LLM 调用封装 — 适配 KBState cost_tracker 的 chat/chat_json/accumulate_usage。

对 pipeline/model_client.py 的薄封装层，提供标准化签名：
  - chat(prompt, system=...) → (text, usage)
  - chat_json(prompt, system=...) → (parsed_json, usage)
  - accumulate_usage(tracker, usage) → None (原地修改)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from pipeline.model_client import Usage, chat_with_retry, create_provider

from tests.cost_guard import BudgetExceededError, CostGuard

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 全局 CostGuard 懒加载
# ---------------------------------------------------------------------------

_cost_guard: CostGuard | None = None


def get_cost_guard() -> CostGuard:
    """获取全局 CostGuard 单例（懒加载）。

    首次调用时从环境变量 BUDGET_YUAN 读取预算上限（默认 1.0 元），
    后续调用复用同一实例。

    Returns:
        全局唯一的 CostGuard 实例。
    """
    global _cost_guard
    if _cost_guard is None:
        budget = float(os.getenv("BUDGET_YUAN", "1.0"))
        _cost_guard = CostGuard(budget_yuan=budget)
        logger.info("CostGuard initialized: budget=¥%.2f", budget)
    return _cost_guard


async def chat(
    prompt: str,
    system: str | None = None,
    temperature: float | None = None,
    node_name: str = "unknown",
) -> tuple[str, Usage]:
    """调用 LLM，返回 (text, usage) 元组。

    Args:
        prompt: 用户消息。
        system: 可选系统提示词。
        temperature: 采样温度，None 表示使用 provider 默认值。
        node_name: 发起调用的 Agent / 节点名称，用于成本追踪。

    Returns:
        (response_text, token_usage) 元组。

    Raises:
        BudgetExceededError: 累计成本超过预算上限时抛出。
    """
    llm = create_provider()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {}
    if temperature is not None:
        kwargs["temperature"] = temperature

    try:
        response = await chat_with_retry(llm, messages, **kwargs)

        guard = get_cost_guard()
        guard.record(
            node_name,
            {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
            model=llm.model,
        )
        guard.check()

        return response.content, response.usage
    finally:
        await llm.close()


def _extract_json(text: str) -> str:
    """清洗 LLM 输出中的 JSON 字符串（处理 markdown fence 等）。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if len(lines) > 1 else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


async def chat_json(
    prompt: str,
    system: str | None = None,
    temperature: float | None = None,
    node_name: str = "unknown",
) -> tuple[dict[str, Any], Usage]:
    """调用 LLM 并强制返回 JSON，返回 (parsed_json, usage) 元组。

    Args:
        prompt: 用户消息。
        system: 可选系统提示词（会追加 JSON-only 约束）。
        temperature: 采样温度。
        node_name: 发起调用的 Agent / 节点名称，透传给 chat()。

    Returns:
        (parsed_dict, token_usage) 元组。
    """
    json_system = (
        (system or "")
        + "\nRespond with valid JSON only. No markdown fences, no extra text."
    )
    text, usage = await chat(
        prompt, system=json_system, temperature=temperature, node_name=node_name
    )
    parsed = json.loads(_extract_json(text))
    return parsed, usage


def accumulate_usage(tracker: dict[str, Any], usage: Usage) -> None:
    """累加单次 LLM 调用的 token 用量到 cost_tracker。

    Args:
        tracker: cost_tracker 字典（原地修改）。
        usage: LLM 调用返回的 Usage 对象。
    """
    tracker["prompt_tokens"] += usage.prompt_tokens
    tracker["completion_tokens"] += usage.completion_tokens
    tracker["total_tokens"] += usage.total_tokens
