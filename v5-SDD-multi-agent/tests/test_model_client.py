"""测试 model_client.py"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# 添加项目根目录到 Python 路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.model_client import (
    Usage,
    LLMResponse,
    OpenAICompatibleProvider,
    CostTracker,
    COST_PER_MILLION_TOKENS_CNY,
    create_provider,
    chat_with_retry,
    estimate_tokens,
    calculate_cost,
    format_cost,
    quick_chat,
    COST_PER_1K_TOKENS,
)


class TestUsage:
    """测试 Usage 数据类"""
    
    def test_auto_calculate_total(self):
        """测试自动计算总 token"""
        usage = Usage(prompt_tokens=100, completion_tokens=200)
        assert usage.total_tokens == 300
    
    def test_manual_total(self):
        """测试手动设置总 token"""
        usage = Usage(prompt_tokens=100, completion_tokens=200, total_tokens=350)
        assert usage.total_tokens == 350
    
    def test_zero_tokens(self):
        """测试零 token"""
        usage = Usage()
        assert usage.total_tokens == 0


class TestLLMResponse:
    """测试 LLMResponse 数据类"""
    
    def test_create_response(self):
        """测试创建响应"""
        usage = Usage(prompt_tokens=100, completion_tokens=200)
        response = LLMResponse(
            content="测试响应",
            usage=usage,
            model="deepseek-chat",
            provider="deepseek"
        )
        assert response.content == "测试响应"
        assert response.usage.total_tokens == 300
        assert response.model == "deepseek-chat"
        assert response.provider == "deepseek"


class TestEstimateTokens:
    """测试 token 估算"""
    
    def test_empty_text(self):
        """测试空文本"""
        assert estimate_tokens("") == 0
    
    def test_english_text(self):
        """测试英文文本"""
        tokens = estimate_tokens("Hello, how are you?")
        assert tokens > 0
    
    def test_chinese_text(self):
        """测试中文文本"""
        tokens = estimate_tokens("你好，请介绍一下自己")
        assert tokens > 0
    
    def test_mixed_text(self):
        """测试混合文本"""
        tokens = estimate_tokens("Hello 你好 World 世界")
        assert tokens > 0


class TestCalculateCost:
    """测试成本计算"""
    
    def test_deepseek_cost(self):
        """测试 DeepSeek 成本"""
        usage = Usage(prompt_tokens=1000, completion_tokens=1000)
        cost = calculate_cost(usage, "deepseek", "deepseek-chat")
        assert cost > 0
    
    def test_qwen_cost(self):
        """测试 Qwen 成本"""
        usage = Usage(prompt_tokens=1000, completion_tokens=1000)
        cost = calculate_cost(usage, "qwen", "qwen-plus")
        assert cost > 0
    
    def test_openai_cost(self):
        """测试 OpenAI 成本"""
        usage = Usage(prompt_tokens=1000, completion_tokens=1000)
        cost = calculate_cost(usage, "openai", "gpt-4o-mini")
        assert cost > 0
    
    def test_unknown_provider(self):
        """测试未知提供商"""
        usage = Usage(prompt_tokens=1000, completion_tokens=1000)
        cost = calculate_cost(usage, "unknown", "unknown")
        assert cost == 0.0
    
    def test_unknown_model(self):
        """测试未知模型"""
        usage = Usage(prompt_tokens=1000, completion_tokens=1000)
        cost = calculate_cost(usage, "deepseek", "unknown")
        assert cost == 0.0


class TestFormatCost:
    """测试成本格式化"""
    
    def test_small_cost(self):
        """测试小成本"""
        result = format_cost(0.0001)
        assert result == "$0.000100"
    
    def test_medium_cost(self):
        """测试中等成本"""
        result = format_cost(0.005)
        assert result == "$0.0050"
    
    def test_large_cost(self):
        """测试大成本"""
        result = format_cost(0.15)
        assert result == "$0.15"


class TestCreateProvider:
    """测试创建提供商"""
    
    def test_create_deepseek(self):
        """测试创建 DeepSeek 提供商"""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            provider = create_provider("deepseek")
            assert provider.get_provider_name() == "deepseek"
            assert provider.get_default_model() == "deepseek-chat"
    
    def test_create_qwen(self):
        """测试创建 Qwen 提供商"""
        with patch.dict(os.environ, {"QWEN_API_KEY": "test-key"}):
            provider = create_provider("qwen")
            assert provider.get_provider_name() == "qwen"
            assert provider.get_default_model() == "qwen-plus"
    
    def test_create_openai(self):
        """测试创建 OpenAI 提供商"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = create_provider("openai")
            assert provider.get_provider_name() == "openai"
            assert provider.get_default_model() == "gpt-4o-mini"
    
    def test_missing_api_key(self):
        """测试缺少 API Key"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="缺少环境变量"):
                create_provider("deepseek")
    
    def test_unsupported_provider(self):
        """测试不支持的提供商"""
        with pytest.raises(ValueError, match="不支持的提供商"):
            create_provider("unsupported")


class TestOpenAICompatibleProvider:
    """测试 OpenAI 兼容提供商"""
    
    def test_chat_success(self):
        """测试成功调用"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "测试响应"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "model": "deepseek-chat"
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch("pipeline.model_client.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            provider = OpenAICompatibleProvider(
                provider_name="deepseek",
                api_key="test-key",
                base_url="https://api.deepseek.com/v1",
                default_model="deepseek-chat"
            )
            
            response = provider.chat("测试提示")
            
            assert response.content == "测试响应"
            assert response.usage.total_tokens == 30
            assert response.provider == "deepseek"


class TestChatWithRetry:
    """测试带重试的调用"""
    
    def test_success_first_try(self):
        """测试第一次成功"""
        mock_provider = MagicMock()
        mock_provider.chat.return_value = LLMResponse(
            content="测试响应",
            usage=Usage(prompt_tokens=10, completion_tokens=20),
            model="deepseek-chat",
            provider="deepseek"
        )
        
        response = chat_with_retry("测试提示", provider=mock_provider)
        assert response.content == "测试响应"
        assert mock_provider.chat.call_count == 1
    
    def test_retry_on_failure(self):
        """测试失败后重试"""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [
            Exception("第一次失败"),
            Exception("第二次失败"),
            LLMResponse(
                content="测试响应",
                usage=Usage(prompt_tokens=10, completion_tokens=20),
                model="deepseek-chat",
                provider="deepseek"
            )
        ]
        
        response = chat_with_retry(
            "测试提示",
            provider=mock_provider,
            max_retries=3
        )
        
        assert response.content == "测试响应"
        assert mock_provider.chat.call_count == 3
    
    def test_all_retries_fail(self):
        """测试所有重试都失败"""
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = Exception("持续失败")

        with pytest.raises(Exception, match="持续失败"):
            chat_with_retry(
                "测试提示",
                provider=mock_provider,
                max_retries=3
            )

        assert mock_provider.chat.call_count == 3


class TestCostTracker:
    """测试 CostTracker 成本追踪器"""

    def test_record_single_call(self):
        """测试记录单次调用"""
        tracker = CostTracker()
        usage = Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        tracker.record(usage, "deepseek")

        # deepseek: 输入 1 元/百万, 输出 2 元/百万
        expected_cost = 1.0 + 2.0
        assert tracker.estimated_cost("deepseek") == pytest.approx(expected_cost)

    def test_record_multiple_providers(self):
        """测试记录多个提供商"""
        tracker = CostTracker()
        usage = Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000)

        tracker.record(usage, "deepseek")
        tracker.record(usage, "qwen")

        # deepseek: 1 + 2 = 3
        assert tracker.estimated_cost("deepseek") == pytest.approx(3.0)
        # qwen: 4 + 12 = 16
        assert tracker.estimated_cost("qwen") == pytest.approx(16.0)
        # 总计
        assert tracker.estimated_cost() == pytest.approx(19.0)

    def test_record_multiple_calls_same_provider(self):
        """测试同一提供商多次调用"""
        tracker = CostTracker()
        usage = Usage(prompt_tokens=500_000, completion_tokens=500_000)

        tracker.record(usage, "deepseek")
        tracker.record(usage, "deepseek")

        # 单次: 0.5 + 1 = 1.5, 两次: 3.0
        assert tracker.estimated_cost("deepseek") == pytest.approx(3.0)

    def test_estimated_cost_no_records(self):
        """测试无记录时成本为 0"""
        tracker = CostTracker()
        assert tracker.estimated_cost() == 0.0
        assert tracker.estimated_cost("deepseek") == 0.0

    def test_record_unknown_provider(self):
        """测试未知提供商"""
        tracker = CostTracker()
        usage = Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000)

        # 未知提供商成本应为 0
        tracker.record(usage, "unknown")
        assert tracker.estimated_cost("unknown") == 0.0

    def test_report_single_provider(self, caplog):
        """测试报告单个提供商"""
        tracker = CostTracker()
        usage = Usage(prompt_tokens=1000, completion_tokens=2000)
        tracker.record(usage, "deepseek")

        with caplog.at_level("INFO"):
            tracker.report("deepseek")

        assert "deepseek" in caplog.text
        assert "调用次数: 1" in caplog.text

    def test_report_all_providers(self, caplog):
        """测试报告所有提供商"""
        tracker = CostTracker()
        usage = Usage(prompt_tokens=1000, completion_tokens=2000)
        tracker.record(usage, "deepseek")
        tracker.record(usage, "qwen")

        with caplog.at_level("INFO"):
            tracker.report()

        assert "deepseek" in caplog.text
        assert "qwen" in caplog.text
        assert "总计调用次数: 2" in caplog.text

    def test_report_empty(self, caplog):
        """测试空报告"""
        tracker = CostTracker()

        with caplog.at_level("INFO"):
            tracker.report()

        assert "无任何调用记录" in caplog.text


class TestCostPerMillionTokensCNY:
    """测试人民币价格表配置"""

    def test_deepseek_prices(self):
        """测试 DeepSeek 价格"""
        assert COST_PER_MILLION_TOKENS_CNY["deepseek"]["input"] == 1.0
        assert COST_PER_MILLION_TOKENS_CNY["deepseek"]["output"] == 2.0

    def test_qwen_prices(self):
        """测试 Qwen 价格"""
        assert COST_PER_MILLION_TOKENS_CNY["qwen"]["input"] == 4.0
        assert COST_PER_MILLION_TOKENS_CNY["qwen"]["output"] == 12.0

    def test_openai_prices(self):
        """测试 OpenAI 价格"""
        assert COST_PER_MILLION_TOKENS_CNY["openai"]["input"] == 150.0
        assert COST_PER_MILLION_TOKENS_CNY["openai"]["output"] == 600.0
