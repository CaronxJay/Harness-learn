"""测试 logger.py"""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from src.logger import JsonFormatter, setup_logger, ProgressTracker


class TestJsonFormatter:
    """测试 JSON 格式化器"""
    
    def test_format_basic(self):
        """测试基本格式化"""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        result = formatter.format(record)
        data = json.loads(result)
        
        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert data["message"] == "Test message"
        assert "timestamp" in data
    
    def test_format_with_exception(self):
        """测试带异常的格式化"""
        formatter = JsonFormatter()
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info
        )
        
        result = formatter.format(record)
        data = json.loads(result)
        
        assert data["level"] == "ERROR"
        assert "exception" in data
        assert "ValueError: Test error" in data["exception"]


class TestSetupLogger:
    """测试设置日志记录器"""
    
    def test_setup_logger_console(self):
        """测试设置控制台日志记录器"""
        logger = setup_logger("test_console")
        
        assert logger.name == "test_console"
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1
    
    def test_setup_logger_with_file(self):
        """测试设置带文件的日志记录器"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            logger = setup_logger("test_file", log_file)
            
            assert logger.name == "test_file"
            assert logger.level == logging.INFO
            assert len(logger.handlers) == 2
            
            # 测试写入日志
            logger.info("Test message")
            
            # 检查文件是否创建
            assert log_file.exists()
            
            # 检查文件内容
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
                data = json.loads(content)
                assert data["message"] == "Test message"


class TestProgressTracker:
    """测试进度追踪器"""
    
    def test_progress_tracker_init(self):
        """测试初始化进度追踪器"""
        tracker = ProgressTracker("test_agent")
        
        assert tracker.agent_name == "test_agent"
        assert tracker.success_count == 0
        assert tracker.fail_count == 0
        assert len(tracker.errors) == 0
    
    def test_progress_tracker_record_success(self):
        """测试记录成功"""
        tracker = ProgressTracker("test_agent")
        tracker.record_success()
        
        assert tracker.success_count == 1
        assert tracker.fail_count == 0
    
    def test_progress_tracker_record_failure(self):
        """测试记录失败"""
        tracker = ProgressTracker("test_agent")
        tracker.record_failure("Test error")
        
        assert tracker.success_count == 0
        assert tracker.fail_count == 1
        assert tracker.errors == ["Test error"]
    
    def test_progress_tracker_get_summary(self):
        """测试获取进度摘要"""
        tracker = ProgressTracker("test_agent")
        tracker.record_success()
        tracker.record_failure("Test error")
        
        summary = tracker.get_summary()
        
        assert summary["agent"] == "test_agent"
        assert summary["success_count"] == 1
        assert summary["fail_count"] == 1
        assert summary["errors"] == ["Test error"]
        assert "start_time" in summary
        assert "end_time" in summary
    
    def test_progress_tracker_log_summary(self):
        """测试记录进度摘要"""
        tracker = ProgressTracker("test_agent")
        tracker.record_success()
        
        logger = logging.getLogger("test_progress")
        logger.setLevel(logging.INFO)
        
        # 添加一个内存处理器来捕获日志
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        
        tracker.log_summary(logger)
