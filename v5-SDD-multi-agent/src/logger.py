"""日志系统模块"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    """JSON 格式的日志格式化器"""
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录
        
        Args:
            record: 日志记录
            
        Returns:
            格式化后的 JSON 字符串
        """
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logger(
    name: str,
    log_file: Path | None = None,
    level: int = logging.INFO
) -> logging.Logger:
    """设置日志记录器
    
    Args:
        name: 日志记录器名称
        log_file: 日志文件路径
        level: 日志级别
        
    Returns:
        日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 清除已有的处理器
    logger.handlers.clear()
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
    
    return logger


class ProgressTracker:
    """进度追踪器"""
    
    def __init__(self, agent_name: str):
        """初始化进度追踪器
        
        Args:
            agent_name: Agent 名称
        """
        self.agent_name = agent_name
        self.start_time = datetime.now()
        self.success_count = 0
        self.fail_count = 0
        self.errors: list[str] = []
    
    def record_success(self) -> None:
        """记录成功"""
        self.success_count += 1
    
    def record_failure(self, error: str) -> None:
        """记录失败
        
        Args:
            error: 错误信息
        """
        self.fail_count += 1
        self.errors.append(error)
    
    def get_summary(self) -> dict[str, Any]:
        """获取进度摘要
        
        Returns:
            进度摘要
        """
        return {
            "agent": self.agent_name,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "errors": self.errors
        }
    
    def log_summary(self, logger: logging.Logger) -> None:
        """记录进度摘要
        
        Args:
            logger: 日志记录器
        """
        summary = self.get_summary()
        logger.info(f"进度摘要: {json.dumps(summary, ensure_ascii=False)}")
