#!/usr/bin/env python3
"""统一的 LLM 调用客户端。

支持 DeepSeek、Qwen、OpenAI 三种模型提供商，通过环境变量切换。
使用 httpx 直接调用 OpenAI 兼容 API，提供重试、Token 估算、成本计算等功能。
"""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

PRICING: dict[str, dict[str, float]] = {
    "deepseek": {"input": 0.27, "output": 1.10},
    "qwen": {"input": 0.40, "output": 1.20},
    "openai": {"input": 2.50, "output": 10.00},
}

PRICING_CNY: dict[str, dict[str, float]] = {
    "deepseek": {"input": 1, "output": 2},
    "qwen": {"input": 4, "output": 12},
    "openai": {"input": 150, "output": 600},
}

DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
    "openai": "gpt-4o",
}

BASE_URLS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "openai": "https://api.openai.com/v1",
}

VALID_PROVIDERS: frozenset[str] = frozenset({"deepseek", "qwen", "openai"})

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    """LLM 调用的 Token 用量统计。

    Attributes:
        prompt_tokens: 输入 Token 数。
        completion_tokens: 输出 Token 数。
        total_tokens: 总 Token 数。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """LLM 调用的统一响应结构。

    Attributes:
        content: 模型返回的文本内容。
        usage: Token 用量统计。
        model: 实际使用的模型名称。
        finish_reason: 完成原因（stop / length / content_filter 等）。
    """

    content: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """LLM 提供商的抽象基类。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """发送对话消息并获取回复。

        Args:
            messages: 对话消息列表，每项含 role 和 content。
            **kwargs: 传递给 API 的额外参数。

        Returns:
            LLMResponse 对象，包含回复内容和用量统计。

        Raises:
            httpx.HTTPError: HTTP 层错误。
        """
        ...


# ---------------------------------------------------------------------------
# OpenAI 兼容实现
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容 API 的通用实现，支持 DeepSeek / Qwen / OpenAI。

    Attributes:
        api_key: API 密钥。
        base_url: API 基础 URL。
        model: 模型名称。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        provider_name: str = "",
    ) -> None:
        """初始化 OpenAI 兼容客户端。

        Args:
            api_key: API 密钥。
            base_url: API 基础 URL（如 https://api.deepseek.com/v1）。
            model: 模型名称。
            timeout: HTTP 请求超时时间，单位秒。
            provider_name: 提供商名称，用于成本跟踪（deepseek / qwen / openai）。
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider_name = provider_name
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """发送对话消息并获取回复。

        Args:
            messages: 对话消息列表。
            temperature: 采样温度，0.0-2.0。
            max_tokens: 最大输出 Token 数。
            **kwargs: 传递给 API 的额外参数（如 top_p, stream 等）。

        Returns:
            LLMResponse 对象。

        Raises:
            httpx.HTTPStatusError: API 返回非 2xx 状态码。
            httpx.RequestError: 网络请求错误。
        """
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(kwargs)

        logger.debug("LLM 请求: %s %s", url, {k: v for k, v in payload.items() if k != "messages"})

        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        usage_data = data.get("usage", {})

        response = LLMResponse(
            content=choice["message"]["content"],
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
            model=data.get("model", self.model),
            finish_reason=choice.get("finish_reason", ""),
        )

        if self.provider_name:
            cost_tracker.record(response.usage, self.provider_name)

        return response

    async def close(self) -> None:
        """关闭底层 HTTP 客户端，释放连接资源。"""
        await self._client.aclose()

    async def __aenter__(self) -> OpenAICompatibleProvider:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Token 估算与成本计算
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """估算文本的 Token 数量。

    使用 UTF-8 字节数除以 3 的启发式方法：
    - 英文约 3 字符 / token
    - 中文约 1 字符 / token

    Args:
        text: 待估算的文本。

    Returns:
        估算的 Token 数量，最小为 1。
    """
    byte_count = len(text.encode("utf-8"))
    return max(1, (byte_count + 2) // 3)


def estimate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    provider: str,
) -> dict[str, float]:
    """估算一次 LLM 调用的费用。

    Args:
        prompt_tokens: 输入 Token 数。
        completion_tokens: 输出 Token 数。
        provider: 提供商名称（deepseek / qwen / openai）。

    Returns:
        字典，包含 input_cost / output_cost / total_cost，单位为 USD。

    Raises:
        ValueError: 提供商名称无效。
    """
    if provider not in PRICING:
        raise ValueError(
            f"不支持的 provider: {provider}，"
            f"有效值: {sorted(PRICING.keys())}"
        )

    pricing = PRICING[provider]
    input_cost = prompt_tokens / 1_000_000 * pricing["input"]
    output_cost = completion_tokens / 1_000_000 * pricing["output"]

    return {
        "input_cost": round(input_cost, 8),
        "output_cost": round(output_cost, 8),
        "total_cost": round(input_cost + output_cost, 8),
        "provider": provider,
        "pricing_input_per_1m": pricing["input"],
        "pricing_output_per_1m": pricing["output"],
    }


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class CostTracker:
    """追踪 LLM 调用的 Token 消耗和成本。

    以人民币（元）为单位，使用国产模型价格表。

    Attributes:
        records: 每次调用的记录列表，每项为 (provider, prompt_tokens, completion_tokens)。
    """

    def __init__(self) -> None:
        """初始化 CostTracker，记录累计 Token 消耗。"""
        self.records: list[dict[str, Any]] = []
        self._input_tokens: dict[str, int] = {}
        self._output_tokens: dict[str, int] = {}

    def record(self, usage: Usage, provider: str) -> None:
        """记录一次 API 调用的 Token 用量。

        Args:
            usage: Usage 对象，包含 prompt_tokens 和 completion_tokens。
            provider: 提供商名称（deepseek / qwen / openai）。
        """
        if provider not in PRICING_CNY:
            logger.warning("CostTracker: 未知 provider '%s'，跳过记录", provider)
            return

        self._input_tokens.setdefault(provider, 0)
        self._output_tokens.setdefault(provider, 0)
        self._input_tokens[provider] += usage.prompt_tokens
        self._output_tokens[provider] += usage.completion_tokens

        self.records.append({
            "provider": provider,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        })

    def estimated_cost(self, provider: str | None = None) -> float:
        """返回累计估算成本（元）。

        Args:
            provider: 提供商名称，为 None 时返回所有提供商的总成本。

        Returns:
            估算的累计成本，单位为人民币元。
        """
        if provider is not None:
            if provider not in self._input_tokens:
                return 0.0
            return self._cost_for(provider)

        total = 0.0
        for p in self._input_tokens:
            total += self._cost_for(p)
        return total

    def _cost_for(self, provider: str) -> float:
        """计算单个提供商的累计成本。"""
        pricing = PRICING_CNY[provider]
        input_tokens = self._input_tokens.get(provider, 0)
        output_tokens = self._output_tokens.get(provider, 0)
        input_cost = input_tokens / 1_000_000 * pricing["input"]
        output_cost = output_tokens / 1_000_000 * pricing["output"]
        return round(input_cost + output_cost, 6)

    def report(self, provider: str | None = None) -> None:
        """打印成本报告。

        Args:
            provider: 提供商名称，为 None 时打印所有提供商的报告。
        """
        print()
        print("=" * 50)
        print("  LLM API 成本报告 (CNY)")
        print("=" * 50)

        providers = [provider] if provider else sorted(self._input_tokens.keys())
        total_input = 0
        total_output = 0
        total_cost = 0.0

        for p in providers:
            if p not in self._input_tokens:
                print(f"  [{p}] 无调用记录")
                continue
            input_t = self._input_tokens.get(p, 0)
            output_t = self._output_tokens.get(p, 0)
            cost = self._cost_for(p)
            calls = sum(1 for r in self.records if r["provider"] == p)

            total_input += input_t
            total_output += output_t
            total_cost += cost

            print(f"  [{p}]")
            print(f"    调用次数 : {calls}")
            print(f"    输入     : {input_t:,} tokens")
            print(f"    输出     : {output_t:,} tokens")
            print(f"    估算成本 : ¥{cost:.6f}")

        if not provider and len(providers) > 1:
            print(f"  {'─' * 46}")
            print(f"  [合计]")
            print(f"    输入     : {total_input:,} tokens")
            print(f"    输出     : {total_output:,} tokens")
            print(f"    估算成本 : ¥{total_cost:.6f}")

        print("=" * 50)
        print()


cost_tracker = CostTracker()
tracker = cost_tracker


# ---------------------------------------------------------------------------
# 高级 API
# ---------------------------------------------------------------------------


async def chat_with_retry(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs: Any,
) -> LLMResponse:
    """带重试机制的 LLM 调用。

    在遇到网络错误或服务器错误时自动重试，使用指数退避策略。
    客户端错误（4xx）不会重试，直接抛出。

    Args:
        provider: LLM 提供商实例。
        messages: 对话消息列表。
        max_retries: 最大重试次数（不含首次调用），共调用 max_retries + 1 次。
        base_delay: 基础延迟秒数，第 n 次重试延迟为 base_delay * 2^n。
        **kwargs: 传递给 provider.chat() 的额外参数。

    Returns:
        LLMResponse 对象。

    Raises:
        httpx.HTTPStatusError: 所有重试后仍失败（5xx），或客户端错误（4xx）直接抛出。
        httpx.RequestError: 所有重试后仍失败的网络错误。
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await provider.chat(messages, **kwargs)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise
            last_exc = exc
        except httpx.RequestError as exc:
            last_exc = exc

        if attempt < max_retries:
            delay = base_delay * (2**attempt)
            logger.warning(
                "LLM 调用失败 (第 %d/%d 次): %s，%.1fs 后重试",
                attempt + 1,
                max_retries + 1,
                last_exc,
                delay,
            )
            await asyncio.sleep(delay)

    logger.error(
        "LLM 调用最终失败 (已重试 %d 次): %s",
        max_retries,
        last_exc,
    )
    raise last_exc  # type: ignore[misc]


def _get_api_key(provider_name: str) -> str:
    """从环境变量获取指定提供商的 API Key。

    优先级：{PROVIDER}_API_KEY > API_KEY

    Args:
        provider_name: 提供商名称。

    Returns:
        API Key 字符串。

    Raises:
        ValueError: 未找到对应的 API Key。
    """
    key = os.getenv(f"{provider_name.upper()}_API_KEY") or os.getenv("API_KEY", "")
    if not key:
        raise ValueError(
            f"缺少 {provider_name} 的 API Key，"
            f"请设置 {provider_name.upper()}_API_KEY 或 API_KEY 环境变量"
        )
    return key


def _resolve_provider(provider: str | None = None) -> str:
    """解析提供商名称，默认从环境变量 LLM_PROVIDER 读取。

    Args:
        provider: 提供商名称，为 None 时使用环境变量。

    Returns:
        提供商名称。

    Raises:
        ValueError: 提供商名称无效。
    """
    name = provider or os.getenv("LLM_PROVIDER", "deepseek")
    if name not in VALID_PROVIDERS:
        raise ValueError(
            f"不支持的 provider: {name}，"
            f"有效值: {sorted(VALID_PROVIDERS)}"
        )
    return name


def create_provider(provider: str | None = None) -> OpenAICompatibleProvider:
    """根据环境配置创建 LLM 提供商实例。

    整合提供商解析和 API Key 获取，一键创建可用的客户端。

    Args:
        provider: 提供商名称（deepseek / qwen / openai），
                  为 None 时从 LLM_PROVIDER 环境变量读取。

    Returns:
        配置好的 OpenAICompatibleProvider 实例。

    Raises:
        ValueError: 提供商无效或缺少 API Key。
    """
    provider_name = _resolve_provider(provider)
    api_key = _get_api_key(provider_name)
    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=BASE_URLS[provider_name],
        model=DEFAULT_MODELS[provider_name],
        provider_name=provider_name,
    )


async def quick_chat(
    prompt: str,
    provider: str | None = None,
    system: str | None = None,
) -> str:
    """快捷调用 LLM，发送单条消息并返回文本回复。

    Args:
        prompt: 用户消息内容。
        provider: 提供商名称（deepseek / qwen / openai），
                  默认从 LLM_PROVIDER 环境变量读取。
        system: 可选的系统提示词。

    Returns:
        模型回复的文本内容。

    Raises:
        ValueError: 提供商无效或缺少 API Key。
        httpx.HTTPError: API 调用失败。
    """
    provider_name = _resolve_provider(provider)
    api_key = _get_api_key(provider_name)

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    llm = OpenAICompatibleProvider(
        api_key=api_key,
        base_url=BASE_URLS[provider_name],
        model=DEFAULT_MODELS[provider_name],
        provider_name=provider_name,
    )

    try:
        response = await chat_with_retry(llm, messages)
        return response.content
    finally:
        await llm.close()


# ---------------------------------------------------------------------------
# 测试入口
# ---------------------------------------------------------------------------


def _run_tests() -> None:
    """运行模块自测。"""
    print("=" * 60)
    print("  pipeline/model_client.py 功能测试")
    print("=" * 60)

    # --- Token 估算测试 ---
    print("\n[1] Token 估算测试")
    test_cases = [
        ("Hello, how are you today?", "英文短句"),
        ("这是一段中文测试文本，用于验证 Token 估算功能。", "中文短句"),
        (
            "AI agents are autonomous systems powered by large language models "
            "that can perceive, reason, and act in complex environments.",
            "英文技术文本",
        ),
        ("", "空字符串"),
    ]
    for text, label in test_cases:
        tokens = estimate_tokens(text)
        print(f"    [{label}] chars={len(text):3d}  →  tokens={tokens}")

    # --- 成本计算测试 ---
    print("\n[2] 成本估算测试 (1000 input + 500 output tokens)")
    for p in ["deepseek", "qwen", "openai"]:
        cost = estimate_cost(1000, 500, p)
        print(
            f"    [{p:>10}] "
            f"input=${cost['input_cost']:.6f}  "
            f"output=${cost['output_cost']:.6f}  "
            f"total=${cost['total_cost']:.6f}"
        )

    # --- Usages 数据类测试 ---
    print("\n[3] 数据模型测试")
    usage = Usage(prompt_tokens=150, completion_tokens=80, total_tokens=230)
    print(f"    Usage: {usage}")

    resp = LLMResponse(
        content="Hello!",
        usage=usage,
        model="deepseek-chat",
        finish_reason="stop",
    )
    print(f"    LLMResponse: content='{resp.content}', model={resp.model}")

    # --- 环境检测 ---
    print("\n[4] 环境检测")
    current_provider = os.getenv("LLM_PROVIDER", "deepseek")
    print(f"    LLM_PROVIDER = {current_provider}")

    api_key = os.getenv(f"{current_provider.upper()}_API_KEY") or os.getenv(
        "API_KEY", ""
    )

    if api_key:
        masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else "****"
        print(f"    {current_provider.upper()}_API_KEY = {masked}")
        print("\n    运行实时调用测试...")

        async def _live_test() -> None:
            try:
                result = await quick_chat(
                    prompt='Reply exactly "OK" and nothing else.',
                    system="You are a test bot. Be minimal.",
                )
                print(f"    实时调用成功: {result}")
            except Exception as exc:
                print(f"    实时调用失败: {exc}")

        asyncio.run(_live_test())
    else:
        print(f"    未检测到 {current_provider.upper()}_API_KEY 或 API_KEY")
        print(f"    跳过实时调用测试。")
        print(f"    请设置环境变量后重试。")

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)


if __name__ == "__main__":
    _run_tests()
