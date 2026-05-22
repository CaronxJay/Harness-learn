"""测试 rss_loader.py"""

import tempfile
from pathlib import Path

import pytest
import yaml

# 添加项目根目录到 Python 路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.rss_loader import (
    RSSSource,
    load_rss_sources,
    get_enabled_sources,
    get_sources_by_category,
    get_all_categories,
)


class TestRSSSource:
    """测试 RSSSource 数据类"""
    
    def test_create_source(self):
        """测试创建数据源"""
        source = RSSSource(
            name="测试源",
            url="https://example.com/rss",
            category="测试分类",
            enabled=True
        )
        assert source.name == "测试源"
        assert source.url == "https://example.com/rss"
        assert source.category == "测试分类"
        assert source.enabled is True
    
    def test_str_enabled(self):
        """测试启用状态的字符串表示"""
        source = RSSSource(
            name="测试源",
            url="https://example.com/rss",
            category="测试分类",
            enabled=True
        )
        assert str(source) == "[✓] 测试源 (测试分类)"
    
    def test_str_disabled(self):
        """测试禁用状态的字符串表示"""
        source = RSSSource(
            name="测试源",
            url="https://example.com/rss",
            category="测试分类",
            enabled=False
        )
        assert str(source) == "[✗] 测试源 (测试分类)"


class TestLoadRssSources:
    """测试加载 RSS 数据源"""
    
    def test_load_valid_config(self):
        """测试加载有效配置"""
        config = {
            "sources": [
                {
                    "name": "测试源1",
                    "url": "https://example1.com/rss",
                    "category": "分类A",
                    "enabled": True
                },
                {
                    "name": "测试源2",
                    "url": "https://example2.com/rss",
                    "category": "分类B",
                    "enabled": False
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()
            
            sources = load_rss_sources(Path(f.name))
            assert len(sources) == 2
            assert sources[0].name == "测试源1"
            assert sources[0].enabled is True
            assert sources[1].name == "测试源2"
            assert sources[1].enabled is False
    
    def test_load_missing_fields(self):
        """测试加载缺少字段的配置"""
        config = {
            "sources": [
                {
                    "name": "测试源"
                    # 缺少 url、category、enabled
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()
            
            sources = load_rss_sources(Path(f.name))
            assert len(sources) == 1
            assert sources[0].name == "测试源"
            assert sources[0].url == ""
            assert sources[0].category == ""
            assert sources[0].enabled is True  # 默认启用
    
    def test_load_empty_config(self):
        """测试加载空配置"""
        config = {"sources": []}
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()
            
            sources = load_rss_sources(Path(f.name))
            assert len(sources) == 0
    
    def test_load_not_found(self):
        """测试加载不存在的文件"""
        with pytest.raises(FileNotFoundError):
            load_rss_sources(Path("/tmp/nonexistent.yaml"))
    
    def test_load_invalid_yaml(self):
        """测试加载无效 YAML"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            f.flush()
            
            with pytest.raises(yaml.YAMLError):
                load_rss_sources(Path(f.name))


class TestGetEnabledSources:
    """测试获取启用的数据源"""
    
    def test_get_enabled(self):
        """测试获取启用的数据源"""
        config = {
            "sources": [
                {"name": "源1", "url": "https://1.com", "category": "A", "enabled": True},
                {"name": "源2", "url": "https://2.com", "category": "A", "enabled": False},
                {"name": "源3", "url": "https://3.com", "category": "B", "enabled": True}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()
            
            enabled = get_enabled_sources(Path(f.name))
            assert len(enabled) == 2
            assert enabled[0].name == "源1"
            assert enabled[1].name == "源3"


class TestGetSourcesByCategory:
    """测试按分类获取数据源"""
    
    def test_get_by_category(self):
        """测试按分类获取数据源"""
        config = {
            "sources": [
                {"name": "源1", "url": "https://1.com", "category": "A", "enabled": True},
                {"name": "源2", "url": "https://2.com", "category": "B", "enabled": True},
                {"name": "源3", "url": "https://3.com", "category": "A", "enabled": False}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()
            
            sources_a = get_sources_by_category("A", Path(f.name))
            assert len(sources_a) == 2
            assert sources_a[0].name == "源1"
            assert sources_a[1].name == "源3"
            
            sources_b = get_sources_by_category("B", Path(f.name))
            assert len(sources_b) == 1
            assert sources_b[0].name == "源2"
            
            sources_c = get_sources_by_category("C", Path(f.name))
            assert len(sources_c) == 0


class TestGetAllCategories:
    """测试获取所有分类"""
    
    def test_get_categories(self):
        """测试获取所有分类"""
        config = {
            "sources": [
                {"name": "源1", "url": "https://1.com", "category": "A", "enabled": True},
                {"name": "源2", "url": "https://2.com", "category": "B", "enabled": True},
                {"name": "源3", "url": "https://3.com", "category": "A", "enabled": False}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config, f)
            f.flush()
            
            categories = get_all_categories(Path(f.name))
            assert len(categories) == 2
            assert "A" in categories
            assert "B" in categories
