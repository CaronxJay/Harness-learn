"""测试 check_quality.py"""

import json
import tempfile
from pathlib import Path

import pytest

# 添加项目根目录到 Python 路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from hooks.check_quality import (
    check_summary_quality,
    check_tech_depth,
    check_format_compliance,
    check_tag_precision,
    check_buzzwords,
    check_entry_quality,
    validate_file,
    DimensionScore,
    QualityReport,
    VALID_TAGS,
    TECH_KEYWORDS,
    BUZZWORDS,
)


class TestCheckSummaryQuality:
    """测试摘要质量检查"""
    
    def test_long_summary_with_keywords(self):
        """测试长摘要含技术关键词"""
        entry = {"summary": "这是一个使用 LLM 和 Agent 技术的项目，用于构建智能对话系统，支持多种模型和工具集成，提供完整的开发框架"}
        result = check_summary_quality(entry)
        assert result.score == 25
        assert result.name == "摘要质量"
    
    def test_medium_summary(self):
        """测试中等长度摘要"""
        entry = {"summary": "这是一个测试项目，用于验证质量评分功能是否正常工作，包含基本的功能测试"}
        result = check_summary_quality(entry)
        assert result.score >= 10
        assert result.name == "摘要质量"
    
    def test_short_summary(self):
        """测试短摘要"""
        entry = {"summary": "太短"}
        result = check_summary_quality(entry)
        assert result.score == 0
    
    def test_empty_summary(self):
        """测试空摘要"""
        entry = {"summary": ""}
        result = check_summary_quality(entry)
        assert result.score == 0
    
    def test_no_summary(self):
        """测试无摘要字段"""
        entry = {}
        result = check_summary_quality(entry)
        assert result.score == 0


class TestCheckTechDepth:
    """测试技术深度检查"""
    
    def test_high_score(self):
        """测试高分"""
        entry = {"score": 9}
        result = check_tech_depth(entry)
        assert result.score == 22  # 9 * 2.5 = 22
    
    def test_medium_score(self):
        """测试中等分数"""
        entry = {"score": 5}
        result = check_tech_depth(entry)
        assert result.score == 12  # 5 * 2.5 = 12
    
    def test_low_score(self):
        """测试低分"""
        entry = {"score": 2}
        result = check_tech_depth(entry)
        assert result.score == 5  # 2 * 2.5 = 5
    
    def test_no_score(self):
        """测试无 score 字段"""
        entry = {}
        result = check_tech_depth(entry)
        assert result.score == 10  # 默认 10 分
    
    def test_invalid_score_type(self):
        """测试无效的 score 类型"""
        entry = {"score": "invalid"}
        result = check_tech_depth(entry)
        assert result.score == 0


class TestCheckFormatCompliance:
    """测试格式规范检查"""
    
    def test_all_fields_present(self):
        """测试所有字段都存在"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "status": "analyzed",
            "collected_at": "2026-05-21T08:00:00Z"
        }
        result = check_format_compliance(entry)
        assert result.score == 20
    
    def test_some_fields_missing(self):
        """测试部分字段缺失"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目"
        }
        result = check_format_compliance(entry)
        assert result.score == 8  # id + title
    
    def test_no_fields(self):
        """测试无字段"""
        entry = {}
        result = check_format_compliance(entry)
        assert result.score == 0


class TestCheckTagPrecision:
    """测试标签精度检查"""
    
    def test_optimal_tags(self):
        """测试最佳标签数量"""
        entry = {"tags": ["llm", "agent", "rag"]}
        result = check_tag_precision(entry)
        assert result.score == 15
    
    def test_too_many_tags(self):
        """测试标签过多"""
        entry = {"tags": ["llm", "agent", "rag", "tool", "framework", "application"]}
        result = check_tag_precision(entry)
        assert result.score == 5  # > 5 个合法标签，5 分
    
    def test_no_tags(self):
        """测试无标签"""
        entry = {"tags": []}
        result = check_tag_precision(entry)
        assert result.score == 0
    
    def test_invalid_tags(self):
        """测试非法标签"""
        entry = {"tags": ["llm", "invalid-tag"]}
        result = check_tag_precision(entry)
        assert result.score == 13  # 15 - 2 = 13
    
    def test_tags_not_list(self):
        """测试 tags 不是数组"""
        entry = {"tags": "llm"}
        result = check_tag_precision(entry)
        assert result.score == 0


class TestCheckBuzzwords:
    """测试空洞词检测"""
    
    def test_no_buzzwords(self):
        """测试无空洞词"""
        entry = {"summary": "这是一个测试项目"}
        result = check_buzzwords(entry)
        assert result.score == 15
    
    def test_chinese_buzzwords(self):
        """测试中文空洞词"""
        entry = {"summary": "这个项目可以赋能开发者，打造全链路解决方案"}
        result = check_buzzwords(entry)
        assert result.score == 9  # 15 - 6 = 9
    
    def test_english_buzzwords(self):
        """测试英文空洞词"""
        entry = {"summary": "This is a groundbreaking and revolutionary project"}
        result = check_buzzwords(entry)
        assert result.score == 9  # 15 - 6 = 9
    
    def test_multiple_buzzwords(self):
        """测试多个空洞词"""
        entry = {"summary": "赋能、抓手、闭环、打通、全链路、底层逻辑"}
        result = check_buzzwords(entry)
        assert result.score == 0  # 15 - 18 = -3, 但最小为 0


class TestCheckEntryQuality:
    """测试条目质量检查"""
    
    def test_high_quality_entry(self):
        """测试高质量条目"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "status": "analyzed",
            "collected_at": "2026-05-21T08:00:00Z",
            "summary": "这是一个使用 LLM 和 Agent 技术的项目，用于构建智能对话系统，支持多种模型和工具集成",
            "tags": ["llm", "agent"],
            "score": 8
        }
        report = check_entry_quality(entry, Path("test.json"))
        assert report.grade == "A"
        assert report.total_score >= 80
    
    def test_medium_quality_entry(self):
        """测试中等质量条目"""
        entry = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "status": "analyzed",
            "collected_at": "2026-05-21T08:00:00Z",
            "summary": "这是一个测试项目，用于验证质量评分功能",
            "tags": ["llm"],
            "score": 5
        }
        report = check_entry_quality(entry, Path("test.json"))
        assert report.grade in ["A", "B"]
        assert report.total_score >= 60
    
    def test_low_quality_entry(self):
        """测试低质量条目"""
        entry = {
            "summary": "太短",
            "tags": []
        }
        report = check_entry_quality(entry, Path("test.json"))
        assert report.grade == "C"
        assert report.total_score < 60


class TestValidateFile:
    """测试文件校验"""
    
    def test_valid_file(self):
        """测试有效文件"""
        data = {
            "id": "github-20260521-001",
            "title": "测试项目",
            "source_url": "https://github.com/test/project",
            "status": "analyzed",
            "collected_at": "2026-05-21T08:00:00Z",
            "summary": "这是一个使用 LLM 和 Agent 技术的项目，用于构建智能对话系统",
            "tags": ["llm", "agent"],
            "score": 8
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            reports = validate_file(Path(f.name))
            assert len(reports) == 1
            assert reports[0].grade in ["A", "B"]
    
    def test_array_file(self):
        """测试数组文件"""
        data = [
            {
                "id": "github-20260521-001",
                "title": "测试项目1",
                "source_url": "https://github.com/test/project1",
                "status": "analyzed",
                "collected_at": "2026-05-21T08:00:00Z",
                "summary": "这是一个使用 LLM 和 Agent 技术的项目，用于构建智能对话系统",
                "tags": ["llm"],
                "score": 8
            },
            {
                "id": "github-20260521-002",
                "title": "测试项目2",
                "source_url": "https://github.com/test/project2",
                "status": "analyzed",
                "collected_at": "2026-05-21T08:00:00Z",
                "summary": "短",
                "tags": [],
                "score": 2
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            reports = validate_file(Path(f.name))
            assert len(reports) == 2
    
    def test_invalid_json(self):
        """测试无效 JSON"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json")
            f.flush()
            
            reports = validate_file(Path(f.name))
            assert len(reports) == 0
    
    def test_not_found(self):
        """测试不存在的文件"""
        reports = validate_file(Path("/tmp/nonexistent.json"))
        assert len(reports) == 0
