"""测试 error_handler.py"""

import logging

import pytest

from src.error_handler import ErrorCategory, ErrorHandler, with_retry


class TestErrorHandler:
    """测试错误处理器"""
    
    def test_handle_error(self):
        """测试处理错误"""
        logger = logging.getLogger("test_error")
        handler = ErrorHandler(logger)
        
        # 添加一个内存处理器来捕获日志
        log_handler = logging.StreamHandler()
        log_handler.setLevel(logging.ERROR)
        logger.addHandler(log_handler)
        logger.setLevel(logging.ERROR)
        
        error = ValueError("Test error")
        context = {"key": "value"}
        
        handler.handle_error(error, ErrorCategory.API_CALL, context)
    
    def test_handle_api_error(self):
        """测试处理 API 错误"""
        logger = logging.getLogger("test_api_error")
        handler = ErrorHandler(logger)
        
        # 添加一个内存处理器来捕获日志
        log_handler = logging.StreamHandler()
        log_handler.setLevel(logging.ERROR)
        logger.addHandler(log_handler)
        logger.setLevel(logging.ERROR)
        
        error = Exception("API Error")
        
        handler.handle_api_error(error, "GitHub API", "/search/repositories")
    
    def test_handle_data_format_error(self):
        """测试处理数据格式错误"""
        logger = logging.getLogger("test_data_error")
        handler = ErrorHandler(logger)
        
        # 添加一个内存处理器来捕获日志
        log_handler = logging.StreamHandler()
        log_handler.setLevel(logging.ERROR)
        logger.addHandler(log_handler)
        logger.setLevel(logging.ERROR)
        
        error = ValueError("Invalid format")
        data = {"key": "value"}
        
        handler.handle_data_format_error(error, data, "JSON array")
    
    def test_handle_file_operation_error(self):
        """测试处理文件操作错误"""
        logger = logging.getLogger("test_file_error")
        handler = ErrorHandler(logger)
        
        # 添加一个内存处理器来捕获日志
        log_handler = logging.StreamHandler()
        log_handler.setLevel(logging.ERROR)
        logger.addHandler(log_handler)
        logger.setLevel(logging.ERROR)
        
        error = FileNotFoundError("File not found")
        
        handler.handle_file_operation_error(error, "/tmp/test.json", "read")


class TestWithRetry:
    """测试带重试的函数执行"""
    
    def test_with_retry_success(self):
        """测试成功执行"""
        call_count = 0
        
        def func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = with_retry(func, max_retries=3)
        
        assert result == "success"
        assert call_count == 1
    
    def test_with_retry_failure_then_success(self):
        """测试失败后成功"""
        call_count = 0
        
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return "success"
        
        result = with_retry(func, max_retries=3, retry_delay=0.01)
        
        assert result == "success"
        assert call_count == 3
    
    def test_with_retry_all_failures(self):
        """测试全部失败"""
        call_count = 0
        
        def func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fail")
        
        with pytest.raises(ValueError):
            with_retry(func, max_retries=3, retry_delay=0.01)
        
        assert call_count == 4  # 初始尝试 + 3 次重试
    
    def test_with_retry_with_error_handler(self):
        """测试带错误处理器的重试"""
        call_count = 0
        logger = logging.getLogger("test_retry")
        logger.setLevel(logging.ERROR)
        
        # 添加一个内存处理器来捕获日志
        log_handler = logging.StreamHandler()
        log_handler.setLevel(logging.ERROR)
        logger.addHandler(log_handler)
        
        error_handler = ErrorHandler(logger)
        
        def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return "success"
        
        result = with_retry(func, max_retries=3, retry_delay=0.01, error_handler=error_handler)
        
        assert result == "success"
        assert call_count == 3
