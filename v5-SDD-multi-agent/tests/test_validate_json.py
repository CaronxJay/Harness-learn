"""测试 validate_json.py"""

import json
import tempfile
from pathlib import Path

import pytest

# 添加项目根目录到 Python 路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from hooks.validate_json import (
    load_schema,
    detect_schema_type,
    validate_json_parse,
    validate_schema,
    validate_custom_rules,
    validate_file,
    ValidationError,
    RAW_SCHEMA_FILE,
    ARTICLE_SCHEMA_FILE,
    ID_PATTERN,
    URL_PATTERN,
)


class TestLoadSchema:
    """测试加载 Schema"""
    
    def test_load_raw_schema(self):
        """测试加载 raw Schema"""
        schema = load_schema(RAW_SCHEMA_FILE)
        assert schema is not None
        assert "items" in schema
        assert "properties" in schema["items"]
    
    def test_load_article_schema(self):
        """测试加载 article Schema"""
        schema = load_schema(ARTICLE_SCHEMA_FILE)
        assert schema is not None
        assert "properties" in schema
        assert "required" in schema
    
    def test_load_not_found(self):
        """测试加载不存在的 Schema"""
        with pytest.raises(FileNotFoundError):
            load_schema(Path("/tmp/nonexistent.json"))


class TestDetectSchemaType:
    """测试检测 Schema 类型"""
    
    def test_detect_raw(self):
        """测试检测 raw 类型"""
        data = [{"title": "test"}]
        assert detect_schema_type(data) == "raw"
    
    def test_detect_article(self):
        """测试检测 article 类型"""
        data = {"title": "test"}
        assert detect_schema_type(data) == "article"


class TestValidateJsonParse:
    """测试 JSON 解析"""
    
    def test_parse_valid_object(self):
        """测试解析有效的对象"""
        data = {"id": "github-20260521-001"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result, errors = validate_json_parse(Path(f.name))
            assert len(errors) == 0
            assert result["id"] == "github-20260521-001"
    
    def test_parse_valid_array(self):
        """测试解析有效的数组"""
        data = [
            {"id": "github-20260521-001"},
            {"id": "github-20260521-002"}
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result, errors = validate_json_parse(Path(f.name))
            assert len(errors) == 0
            assert len(result) == 2
    
    def test_parse_invalid_json(self):
        """测试解析无效的 JSON"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json")
            f.flush()
            
            result, errors = validate_json_parse(Path(f.name))
            assert len(errors) == 1
            assert "JSON 解析失败" in errors[0].message
    
    def test_parse_not_found(self):
        """测试解析不存在的文件"""
        result, errors = validate_json_parse(Path("/tmp/nonexistent.json"))
        assert len(errors) == 1
        assert "文件不存在" in errors[0].message


class TestValidateSchema:
    """测试 Schema 校验"""
    
    def test_validate_raw_valid(self):
        """测试有效的 raw 数据"""
        schema = load_schema(RAW_SCHEMA_FILE)
        
        data = [
            {
                "title": "test-project",
                "url": "https://github.com/test/project",
                "source": "github",
                "popularity": 100,
                "summary": "测试项目"
            }
        ]
        
        errors = validate_schema(data, schema, Path("test.json"))
        assert len(errors) == 0
    
    def test_validate_raw_missing_field(self):
        """测试缺少必填字段的 raw 数据"""
        schema = load_schema(RAW_SCHEMA_FILE)
        
        data = [
            {
                "title": "test-project",
                "url": "https://github.com/test/project",
                # 缺少 source
                "popularity": 100,
                "summary": "测试项目"
            }
        ]
        
        errors = validate_schema(data, schema, Path("test.json"))
        assert len(errors) > 0
    
    def test_validate_raw_invalid_source(self):
        """测试无效 source 的 raw 数据"""
        schema = load_schema(RAW_SCHEMA_FILE)
        
        data = [
            {
                "title": "test-project",
                "url": "https://github.com/test/project",
                "source": "invalid",  # 无效的 source
                "popularity": 100,
                "summary": "测试项目"
            }
        ]
        
        errors = validate_schema(data, schema, Path("test.json"))
        assert len(errors) > 0
    
    def test_validate_article_valid(self):
        """测试有效的 article 数据"""
        schema = load_schema(ARTICLE_SCHEMA_FILE)
        
        data = {
            "id": "github-20260521-001",
            "title": "test-project",
            "source_url": "https://github.com/test/project",
            "source_type": "github",
            "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作",
            "tags": ["llm", "agent"],
            "tech_direction": "llm",
            "quality_level": "A",
            "use_case": "开发者可以用这个工具",
            "status": "analyzed",
            "collected_at": "2026-05-21T08:00:00Z"
        }
        
        errors = validate_schema(data, schema, Path("test.json"))
        assert len(errors) == 0
    
    def test_validate_article_missing_field(self):
        """测试缺少必填字段的 article 数据"""
        schema = load_schema(ARTICLE_SCHEMA_FILE)
        
        data = {
            "id": "github-20260521-001",
            "title": "test-project",
            "source_url": "https://github.com/test/project",
            # 缺少 source_type
            "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作",
            "tags": ["llm", "agent"],
            "tech_direction": "llm",
            "quality_level": "A",
            "use_case": "开发者可以用这个工具",
            "status": "analyzed",
            "collected_at": "2026-05-21T08:00:00Z"
        }
        
        errors = validate_schema(data, schema, Path("test.json"))
        assert len(errors) > 0


class TestValidateCustomRules:
    """测试自定义规则校验"""
    
    def test_valid_entry(self):
        """测试有效条目"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作",
            "tags": ["llm", "agent"],
            "status": "draft"
        }
        
        errors = validate_custom_rules(entry, Path("test.json"))
        assert len(errors) == 0
    
    def test_invalid_id_format(self):
        """测试无效的 ID 格式"""
        entry = {
            "id": "invalid-id",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作",
            "tags": ["llm", "agent"],
            "status": "draft"
        }
        
        errors = validate_custom_rules(entry, Path("test.json"))
        assert len(errors) == 1
        assert "ID 格式错误" in errors[0].message
    
    def test_invalid_url(self):
        """测试无效的 URL"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "invalid-url",
            "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作",
            "tags": ["llm", "agent"],
            "status": "draft"
        }
        
        errors = validate_custom_rules(entry, Path("test.json"))
        assert len(errors) == 1
        assert "URL 格式错误" in errors[0].message
    
    def test_short_summary(self):
        """测试过短的摘要"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "summary": "太短",
            "tags": ["llm", "agent"],
            "status": "draft"
        }
        
        errors = validate_custom_rules(entry, Path("test.json"))
        assert len(errors) == 1
        assert "摘要过短" in errors[0].message
    
    def test_empty_tags(self):
        """测试空标签"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作",
            "tags": [],
            "status": "draft"
        }
        
        errors = validate_custom_rules(entry, Path("test.json"))
        assert len(errors) == 1
        assert "标签数量不足" in errors[0].message
    
    def test_invalid_score(self):
        """测试无效的 score"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作",
            "tags": ["llm", "agent"],
            "status": "draft",
            "score": 11
        }
        
        errors = validate_custom_rules(entry, Path("test.json"))
        assert len(errors) == 1
        assert "score 范围错误" in errors[0].message
    
    def test_invalid_audience(self):
        """测试无效的 audience"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作",
            "tags": ["llm", "agent"],
            "status": "draft",
            "audience": "invalid"
        }
        
        errors = validate_custom_rules(entry, Path("test.json"))
        assert len(errors) == 1
        assert "audience 值无效" in errors[0].message


class TestValidateFile:
    """测试文件校验"""
    
    def test_validate_raw_file(self):
        """测试校验 raw 文件"""
        data = [
            {
                "title": "test-project",
                "url": "https://github.com/test/project",
                "source": "github",
                "popularity": 100,
                "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作"
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            errors = validate_file(Path(f.name), "raw")
            assert len(errors) == 0
    
    def test_validate_article_file(self):
        """测试校验 article 文件"""
        data = {
            "id": "github-20260521-001",
            "title": "test-project",
            "source_url": "https://github.com/test/project",
            "source_type": "github",
            "summary": "这是一个测试项目，用于验证 JSON 格式校验功能是否正常工作",
            "tags": ["llm", "agent"],
            "tech_direction": "llm",
            "quality_level": "A",
            "use_case": "开发者可以用这个工具",
            "status": "analyzed",
            "collected_at": "2026-05-21T08:00:00Z"
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            errors = validate_file(Path(f.name), "article")
            assert len(errors) == 0
    
    def test_validate_invalid_json_file(self):
        """测试校验无效 JSON 文件"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json")
            f.flush()
            
            errors = validate_file(Path(f.name), "raw")
            assert len(errors) > 0
    
    def test_validate_not_found_file(self):
        """测试校验不存在的文件"""
        errors = validate_file(Path("/tmp/nonexistent.json"), "raw")
        assert len(errors) > 0


class TestPatterns:
    """测试正则表达式"""
    
    def test_id_pattern_valid(self):
        """测试有效的 ID 格式"""
        assert ID_PATTERN.match("github-20260521-001")
        assert ID_PATTERN.match("hackernews-20260521-002")
    
    def test_id_pattern_invalid(self):
        """测试无效的 ID 格式"""
        assert not ID_PATTERN.match("invalid-id")
        assert not ID_PATTERN.match("github-20260521")  # 缺少序号
        assert not ID_PATTERN.match("github-2026052-001")  # 日期格式错误
        assert not ID_PATTERN.match("github-20260521-01")  # 序号格式错误
    
    def test_url_pattern_valid(self):
        """测试有效的 URL 格式"""
        assert URL_PATTERN.match("https://github.com/test/project")
        assert URL_PATTERN.match("http://example.com")
    
    def test_url_pattern_invalid(self):
        """测试无效的 URL 格式"""
        assert not URL_PATTERN.match("invalid-url")
        assert not URL_PATTERN.match("ftp://example.com")
        assert not URL_PATTERN.match("github.com/test/project")
