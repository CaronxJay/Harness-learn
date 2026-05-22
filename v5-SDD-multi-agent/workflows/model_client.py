"""LangGraph 工作流 LLM 客户端适配器

封装 pipeline.model_client，提供工作流节点使用的简化接口。
集成 CostGuard 预算守卫，超预算时自动抛出 BudgetExceededError。

使用方法：
    from workflows.model_client import chat, chat_json, accumulate_usage

    text, usage = chat("你好", node_name="analyzer")
    result, usage = chat_json('{"prompt": "..."}', node_name="reviewer")
    accumulate_usage(state["cost_tracker"], usage)
"""

import json
import logging
import os
from typing import Optional, Tuple, Union

from pipeline.model_client import Usage, chat_with_retry, create_provider

logger = logging.getLogger(__name__)


# ============================================================
# CostGuard 懒加载
# ============================================================

_cost_guard = None


def get_cost_guard():
    """获取全局 CostGuard 实例（懒加载）

    第一次调用时创建，后续复用同一实例。
    budget_yuan 从环境变量 BUDGET_YUAN 读取，默认 1.0。
    """
    global _cost_guard
    if _cost_guard is None:
        from tests.cost_guard import CostGuard

        budget = float(os.getenv("BUDGET_YUAN", "1.0"))
        _cost_guard = CostGuard(budget_yuan=budget)
        logger.info(f"[CostGuard] 初始化完成，预算: {budget} 元")
    return _cost_guard


def chat(
    prompt: str,
    system: Optional[str] = None,
    node_name: str = "unknown",
) -> Tuple[str, Usage]:
    """调用 LLM，返回文本和用量

    调用完成后自动记录成本并检查预算，超预算时抛出 BudgetExceededError。

    Args:
        prompt: 用户输入
        system: 系统提示词
        node_name: 调用节点名称，用于成本归类

    Returns:
        (响应文本, Usage) 元组

    Raises:
        BudgetExceededError: 当总成本超出预算时
    """
    provider = create_provider()
    model_name = provider.get_default_model()
    response = chat_with_retry(
        prompt=prompt,
        system_prompt=system,
        provider=provider,
    )
    usage = response.usage

    # 记录成本并检查预算
    guard = get_cost_guard()
    usage_dict = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
    }
    guard.record(node_name, usage_dict, model=model_name)
    guard.check()

    return response.content, usage


def chat_json(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.7,
    node_name: str = "unknown",
) -> Tuple[dict, Usage]:
    """调用 LLM 并解析 JSON 响应

    Args:
        prompt: 用户输入
        system: 系统提示词
        temperature: 温度参数，控制输出随机性
        node_name: 调用节点名称，用于成本归类

    Returns:
        (解析后的字典, Usage) 元组

    Raises:
        BudgetExceededError: 当总成本超出预算时
    """
    provider = create_provider()
    model_name = provider.get_default_model()
    response = chat_with_retry(
        prompt=prompt,
        system_prompt=system,
        temperature=temperature,
        provider=provider,
    )
    usage = response.usage

    # 记录成本并检查预算
    guard = get_cost_guard()
    usage_dict = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
    }
    guard.record(node_name, usage_dict, model=model_name)
    guard.check()

    text = response.content
    text = text.strip()

    # 处理 markdown 代码块包裹的 JSON
    if text.startswith("```"):
        lines = text.split("\n")
        end_idx = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end_idx = i
                break
        text = "\n".join(lines[1:end_idx])

    return json.loads(text), usage


def accumulate_usage(tracker: dict, usage: Usage) -> None:
    """累加 token 统计到 cost_tracker

    Args:
        tracker: KBState["cost_tracker"] 字典
        usage: 单次调用的 Usage 对象
    """
    tracker["total_tokens"] = tracker.get("total_tokens", 0) + usage.total_tokens
    tracker["prompt_tokens"] = tracker.get("prompt_tokens", 0) + usage.prompt_tokens
    tracker["completion_tokens"] = (
        tracker.get("completion_tokens", 0) + usage.completion_tokens
    )
