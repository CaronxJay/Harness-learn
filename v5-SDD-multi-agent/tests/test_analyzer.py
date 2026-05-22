"""测试 analyzer.py"""

import json
import tempfile
from pathlib import Path

import pytest

from src.analyzer import load_raw_data, analyze_raw_data


def test_load_raw_data_valid():
    """测试加载有效的原始数据"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([
            {"title": "Test", "url": "https://example.com", "source": "github", "popularity": 100, "summary": "Test"}
        ], f)
        f.flush()
        
        data = load_raw_data(Path(f.name))
        assert len(data) == 1
        assert data[0]["title"] == "Test"


def test_load_raw_data_empty_file():
    """测试加载空文件"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("[]")
        f.flush()
        
        data = load_raw_data(Path(f.name))
        assert len(data) == 0


def test_load_raw_data_invalid_json():
    """测试加载无效 JSON"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("invalid json")
        f.flush()
        
        data = load_raw_data(Path(f.name))
        assert len(data) == 0


def test_load_raw_data_not_array():
    """测试加载非数组 JSON"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"title": "Test"}, f)
        f.flush()
        
        data = load_raw_data(Path(f.name))
        assert len(data) == 0


def test_load_raw_data_not_found():
    """测试加载不存在的文件"""
    data = load_raw_data(Path("/tmp/nonexistent.json"))
    assert len(data) == 0
