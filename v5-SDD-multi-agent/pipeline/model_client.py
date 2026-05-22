"""统一的 LLM 调用客户端

支持 DeepSeek、Qwen、OpenAI 三种模型提供商，通过环境变量切换。

使用方法：
    from pipeline.model_client import quick_chat, chat_with_retry

    # 快速调用
    response = quick_chat("你好，请介绍一下自己")

    # 带重试的调用
    response = chat_with_retry("你好，请介绍一下自己")

环境变量：
    LLM_PROVIDER: 模型提供商（deepseek/qwen/openai），默认 deepseek
    DEEPSEEK_API_KEY: DeepSeek API Key
    QWEN_API_KEY: Qwen API Key
    OPENAI_API_KEY: OpenAI API Key

编码规范：
    - 遵循 PEP 8
    - Google 风格 docstring
    - 使用 logging 不用 print
"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    import httpx
except ImportError:
    raise ImportError("缺少 httpx 库，请运行: pip install httpx")

# 配置日志
logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Usage:
    """Token 用量统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        """自动计算总 token"""
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    usage: Usage
    model: str
    provider: str
    raw_response: dict = field(default_factory=dict)


# ============================================================
# 成本配置（USD / 1K tokens）
# ============================================================

COST_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "deepseek": {
        "deepseek-chat": {"input": 0.00014, "output": 0.00028},
        "deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
    },
    "qwen": {
        "qwen-turbo": {"input": 0.0003, "output": 0.0006},
        "qwen-plus": {"input": 0.0008, "output": 0.002},
        "qwen-max": {"input": 0.0024, "output": 0.0096},
    },
    "openai": {
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    },
}


# ============================================================
# 抽象基类
# ============================================================

class LLMProvider(ABC):
    """LLM 提供商抽象基类"""

    @abstractmethod
    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """调用 LLM

        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            LLMResponse 对象
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """获取提供商名称"""
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型名称"""
        pass


# ============================================================
# OpenAI 兼容提供商实现
# ============================================================

class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容 API 提供商

    支持 DeepSeek、Qwen、OpenAI 等兼容 OpenAI API 格式的服务。
    """

    def __init__(
        self,
        provider_name: str,
        api_key: str,
        base_url: str,
        default_model: str,
    ):
        """初始化提供商

        Args:
            provider_name: 提供商名称
            api_key: API Key
            base_url: API 基础 URL
            default_model: 默认模型名称
        """
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    def get_provider_name(self) -> str:
        """获取提供商名称"""
        return self.provider_name

    def get_default_model(self) -> str:
        """获取默认模型名称"""
        return self.default_model

    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """调用 LLM

        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            LLMResponse 对象

        Raises:
            httpx.HTTPStatusError: HTTP 错误
            json.JSONDecodeError: JSON 解析错误
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        logger.debug(f"调用 {self.provider_name} API: {url}")
        logger.debug(f"请求参数: model={self.default_model}, temperature={temperature}")

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        # 解析响应
        content = data["choices"][0]["message"]["content"]
        usage_data = data.get("usage", {})

        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return LLMResponse(
            content=content,
            usage=usage,
            model=data.get("model", self.default_model),
            provider=self.provider_name,
            raw_response=data,
        )


# ============================================================
# 提供商工厂
# ============================================================

def create_provider(provider_name: Optional[str] = None) -> LLMProvider:
    """创建 LLM 提供商

    Args:
        provider_name: 提供商名称（deepseek/qwen/openai），默认从环境变量读取

    Returns:
        LLMProvider 实例

    Raises:
        ValueError: 不支持的提供商或缺少 API Key
    """
    if provider_name is None:
        provider_name = os.getenv("LLM_PROVIDER", "deepseek").lower()

    providers = {
        "deepseek": {
            "api_key_env": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-chat",
        },
        "qwen": {
            "api_key_env": "QWEN_API_KEY",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "default_model": "qwen-plus",
        },
        "openai": {
            "api_key_env": "OPENAI_API_KEY",
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-4o-mini",
        },
    }

    if provider_name not in providers:
        raise ValueError(f"不支持的提供商: {provider_name}，支持: {list(providers.keys())}")

    config = providers[provider_name]
    api_key = os.getenv(config["api_key_env"])

    if not api_key:
        raise ValueError(f"缺少环境变量: {config['api_key_env']}")

    return OpenAICompatibleProvider(
        provider_name=provider_name,
        api_key=api_key,
        base_url=config["base_url"],
        default_model=config["default_model"],
    )


# ============================================================
# 带重试的调用函数
# ============================================================

def chat_with_retry(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    max_retries: int = 3,
    provider: Optional[LLMProvider] = None,
) -> LLMResponse:
    """带重试的 LLM 调用

    Args:
        prompt: 用户输入
        system_prompt: 系统提示词
        temperature: 温度参数
        max_tokens: 最大 token 数
        max_retries: 最大重试次数
        provider: LLM 提供商实例，默认自动创建

    Returns:
        LLMResponse 对象

    Raises:
        Exception: 所有重试都失败后的最后一个异常
    """
    if provider is None:
        provider = create_provider()

    last_error = None

    for attempt in range(max_retries):
        try:
            logger.info(f"调用 {provider.get_provider_name()} (尝试 {attempt + 1}/{max_retries})")
            response = provider.chat(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # 调用成功，自动记录到全局成本追踪器
            tracker.record(response.usage, response.provider)
            return response
        except Exception as e:
            last_error = e
            wait_time = 2 ** attempt  # 指数退避: 1s, 2s, 4s
            logger.warning(f"调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            logger.info(f"等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)

    logger.error(f"所有重试都失败，最后一个错误: {last_error}")
    raise last_error


# ============================================================
# 人民币成本配置（元 / 百万 tokens）
# ============================================================

COST_PER_MILLION_TOKENS_CNY: dict[str, dict[str, float]] = {
    "deepseek": {"input": 1.0, "output": 2.0},
    "qwen": {"input": 4.0, "output": 12.0},
    "openai": {"input": 150.0, "output": 600.0},
}


class CostTracker:
    """LLM 调用成本追踪器

    追踪各提供商的 token 消耗和成本，支持按提供商分别统计。

    Example:
        >>> tracker = CostTracker()
        >>> tracker.record(Usage(prompt_tokens=100, completion_tokens=200), "deepseek")
        >>> tracker.estimated_cost("deepseek")
        0.0005
        >>> tracker.report()
    """

    def __init__(self) -> None:
        """初始化成本追踪器"""
        self._records: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def record(self, usage: Usage, provider: str = "deepseek") -> None:
        """记录一次 API 调用

        Args:
            usage: Token 用量统计
            provider: 提供商名称
        """
        cost = self._calculate_cost_cny(usage, provider)
        self._records[provider].append({
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cost_cny": cost,
        })
        logger.debug(
            f"记录 {provider} 调用: {usage.total_tokens} tokens, "
            f"成本 ¥{cost:.4f}"
        )

    def _calculate_cost_cny(self, usage: Usage, provider: str) -> float:
        """计算人民币成本

        Args:
            usage: Token 用量统计
            provider: 提供商名称

        Returns:
            成本（元）
        """
        if provider not in COST_PER_MILLION_TOKENS_CNY:
            logger.warning(f"未找到提供商 {provider} 的人民币成本配置")
            return 0.0

        prices = COST_PER_MILLION_TOKENS_CNY[provider]
        input_cost = (usage.prompt_tokens / 1_000_000) * prices["input"]
        output_cost = (usage.completion_tokens / 1_000_000) * prices["output"]

        return input_cost + output_cost

    def estimated_cost(self, provider: Optional[str] = None) -> float:
        """返回估算成本（元）

        Args:
            provider: 提供商名称，None 表示所有提供商合计

        Returns:
            成本（元）
        """
        if provider is not None:
            return sum(r["cost_cny"] for r in self._records.get(provider, []))

        return sum(
            r["cost_cny"]
            for records in self._records.values()
            for r in records
        )

    def report(self, provider: Optional[str] = None) -> None:
        """打印成本报告

        Args:
            provider: 提供商名称，None 表示报告所有提供商
        """
        if provider is not None:
            self._report_provider(provider)
        else:
            for p in sorted(self._records.keys()):
                self._report_provider(p)
            self._report_total()

    def _report_provider(self, provider: str) -> None:
        """打印单个提供商的报告

        Args:
            provider: 提供商名称
        """
        records = self._records.get(provider, [])
        if not records:
            logger.info(f"[{provider}] 无调用记录")
            return

        total_prompt = sum(r["prompt_tokens"] for r in records)
        total_completion = sum(r["completion_tokens"] for r in records)
        total_cost = sum(r["cost_cny"] for r in records)
        call_count = len(records)

        logger.info(f"[{provider}] 调用次数: {call_count}")
        logger.info(f"[{provider}] 输入 tokens: {total_prompt:,}")
        logger.info(f"[{provider}] 输出 tokens: {total_completion:,}")
        logger.info(f"[{provider}] 总 tokens: {total_prompt + total_completion:,}")
        logger.info(f"[{provider}] 估算成本: ¥{total_cost:.4f}")

    def _report_total(self) -> None:
        """打印总计报告"""
        if not self._records:
            logger.info("无任何调用记录")
            return

        total_cost = self.estimated_cost()
        total_calls = sum(len(r) for r in self._records.values())
        logger.info("=" * 40)
        logger.info(f"总计调用次数: {total_calls}")
        logger.info(f"总计估算成本: ¥{total_cost:.4f}")


# 全局成本追踪器实例
tracker = CostTracker()


# ============================================================
# Token 估算和成本计算
# ============================================================

def estimate_tokens(text: str) -> int:
    """估算文本的 token 数量

    简单估算规则：
    - 英文：约 4 个字符 = 1 token
    - 中文：约 2 个字符 = 1 token
    - 混合文本：取平均值

    Args:
        text: 输入文本

    Returns:
        估算的 token 数量
    """
    if not text:
        return 0

    # 统计中文字符数
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    # 统计英文字符数（去除空格）
    english_chars = len(text) - chinese_chars

    # 估算 token
    chinese_tokens = chinese_chars / 2
    english_tokens = english_chars / 4

    return int(chinese_tokens + english_tokens)


def calculate_cost(
    usage: Usage,
    provider: str = "deepseek",
    model: str = "deepseek-chat",
) -> float:
    """计算 token 消耗成本（USD）

    Args:
        usage: Token 用量统计
        provider: 提供商名称
        model: 模型名称

    Returns:
        成本（USD）
    """
    if provider not in COST_PER_1K_TOKENS:
        logger.warning(f"未找到提供商 {provider} 的成本配置")
        return 0.0

    provider_costs = COST_PER_1K_TOKENS[provider]
    if model not in provider_costs:
        logger.warning(f"未找到模型 {model} 的成本配置")
        return 0.0

    model_costs = provider_costs[model]
    input_cost = (usage.prompt_tokens / 1000) * model_costs["input"]
    output_cost = (usage.completion_tokens / 1000) * model_costs["output"]

    return input_cost + output_cost


def format_cost(cost: float) -> str:
    """格式化成本显示

    Args:
        cost: 成本（USD）

    Returns:
        格式化后的字符串
    """
    if cost < 0.001:
        return f"${cost:.6f}"
    elif cost < 0.01:
        return f"${cost:.4f}"
    else:
        return f"${cost:.2f}"


# ============================================================
# 便捷函数
# ============================================================

def quick_chat(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider_name: Optional[str] = None,
) -> str:
    """快速调用 LLM，返回文本内容

    Args:
        prompt: 用户输入
        system_prompt: 系统提示词
        provider_name: 提供商名称，默认从环境变量读取

    Returns:
        LLM 响应文本

    Example:
        >>> response = quick_chat("你好，请介绍一下自己")
        >>> print(response)
        '你好！我是一个 AI 助手...'
    """
    provider = create_provider(provider_name)
    response = chat_with_retry(
        prompt=prompt,
        system_prompt=system_prompt,
        provider=provider,
    )

    # 记录用量信息
    cost = calculate_cost(response.usage, response.provider, response.model)
    logger.info(
        f"调用完成: {response.usage.total_tokens} tokens, "
        f"成本: {format_cost(cost)}"
    )

    return response.content


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger.info("=" * 60)
    logger.info("LLM 客户端测试")
    logger.info("=" * 60)

    # 测试 token 估算
    test_texts = [
        "Hello, how are you?",
        "你好，请介绍一下自己",
        "这是一个测试，Hello World！",
    ]

    logger.info("\n--- Token 估算测试 ---")
    for text in test_texts:
        tokens = estimate_tokens(text)
        logger.info(f"文本: {text[:20]}... -> 估算 {tokens} tokens")

    # 测试成本计算
    logger.info("\n--- 成本计算测试 ---")
    test_usage = Usage(prompt_tokens=100, completion_tokens=200)
    for provider in ["deepseek", "qwen", "openai"]:
        models = COST_PER_1K_TOKENS.get(provider, {})
        for model in models:
            cost = calculate_cost(test_usage, provider, model)
            logger.info(f"{provider}/{model}: {format_cost(cost)}")

    # 测试 LLM 调用（需要配置 API Key）
    logger.info("\n--- LLM 调用测试 ---")
    try:
        provider = create_provider()
        logger.info(f"使用提供商: {provider.get_provider_name()}")
        logger.info(f"默认模型: {provider.get_default_model()}")

        # 简单测试
        response = chat_with_retry(
            prompt="请用一句话介绍自己",
            max_tokens=100,
            provider=provider,
        )

        logger.info(f"响应内容: {response.content[:100]}...")
        logger.info(f"Token 用量: {response.usage.total_tokens}")
        logger.info(f"模型: {response.model}")

        # 计算成本
        cost = calculate_cost(response.usage, response.provider, response.model)
        logger.info(f"调用成本: {format_cost(cost)}")

    except ValueError as e:
        logger.warning(f"跳过 LLM 调用测试: {e}")
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")

    logger.info("\n测试完成")
