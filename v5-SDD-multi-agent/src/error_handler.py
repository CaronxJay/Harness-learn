"""错误处理模块"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """错误分类"""
    API_CALL = "api_call"
    DATA_FORMAT = "data_format"
    FILE_OPERATION = "file_operation"
    UNKNOWN = "unknown"


class ErrorHandler:
    """错误处理器"""
    
    def __init__(self, logger: logging.Logger | None = None):
        """初始化错误处理器
        
        Args:
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def handle_error(
        self,
        error: Exception,
        category: ErrorCategory,
        context: dict[str, Any] | None = None
    ) -> None:
        """处理错误
        
        Args:
            error: 异常
            category: 错误分类
            context: 上下文信息
        """
        error_info = {
            "category": category.value,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {}
        }
        
        self.logger.error(f"错误发生: {error_info}")
    
    def handle_api_error(
        self,
        error: Exception,
        api_name: str,
        endpoint: str | None = None
    ) -> None:
        """处理 API 调用错误
        
        Args:
            error: 异常
            api_name: API 名称
            endpoint: API 端点
        """
        context = {
            "api_name": api_name,
            "endpoint": endpoint
        }
        self.handle_error(error, ErrorCategory.API_CALL, context)
    
    def handle_data_format_error(
        self,
        error: Exception,
        data: Any,
        expected_format: str | None = None
    ) -> None:
        """处理数据格式错误
        
        Args:
            error: 异常
            data: 数据
            expected_format: 期望的格式
        """
        context = {
            "data_type": type(data).__name__,
            "expected_format": expected_format
        }
        self.handle_error(error, ErrorCategory.DATA_FORMAT, context)
    
    def handle_file_operation_error(
        self,
        error: Exception,
        file_path: str,
        operation: str
    ) -> None:
        """处理文件操作错误
        
        Args:
            error: 异常
            file_path: 文件路径
            operation: 操作类型
        """
        context = {
            "file_path": file_path,
            "operation": operation
        }
        self.handle_error(error, ErrorCategory.FILE_OPERATION, context)


def with_retry(
    func: callable,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    error_handler: ErrorHandler | None = None
) -> Any:
    """带重试的函数执行
    
    Args:
        func: 要执行的函数
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
        error_handler: 错误处理器
        
    Returns:
        函数执行结果
        
    Raises:
        Exception: 最后一次重试的异常
    """
    import time
    
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            
            if attempt < max_retries:
                if error_handler:
                    error_handler.handle_error(
                        e,
                        ErrorCategory.UNKNOWN,
                        {"attempt": attempt + 1, "max_retries": max_retries}
                    )
                time.sleep(retry_delay)
            else:
                if error_handler:
                    error_handler.handle_error(
                        e,
                        ErrorCategory.UNKNOWN,
                        {"attempt": attempt + 1, "max_retries": max_retries, "final_failure": True}
                    )
                raise
