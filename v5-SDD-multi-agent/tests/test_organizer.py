"""测试 organizer.py"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.organizer import (
    load_analyzed_data,
    get_existing_urls,
    check_duplicate,
    format_article,
    generate_filename,
    save_article,
    organize_data
)


class TestLoadAnalyzedData:
    """测试加载已标注数据"""
    
    def test_load_valid_data(self):
        """测试加载有效数据"""
        data = [
            {"title": "test", "url": "https://example.com", "source": "github", "popularity": 100, "summary": "test"}
        ]
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result = load_analyzed_data(Path(f.name))
            assert len(result) == 1
            assert result[0]["title"] == "test"
    
    def test_load_empty_file(self):
        """测试加载空文件"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("[]")
            f.flush()
            
            result = load_analyzed_data(Path(f.name))
            assert len(result) == 0
    
    def test_load_invalid_json(self):
        """测试加载无效 JSON"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json")
            f.flush()
            
            result = load_analyzed_data(Path(f.name))
            assert len(result) == 0
    
    def test_load_not_array(self):
        """测试加载非数组 JSON"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"title": "test"}, f)
            f.flush()
            
            result = load_analyzed_data(Path(f.name))
            assert len(result) == 0
    
    def test_load_not_found(self):
        """测试加载不存在的文件"""
        result = load_analyzed_data(Path("/tmp/nonexistent.json"))
        assert len(result) == 0


class TestGetExistingUrls:
    """测试获取已存在的 URL"""
    
    def test_get_existing_urls(self):
        """测试获取已存在的 URL"""
        with tempfile.TemporaryDirectory() as tmpdir:
            articles_dir = Path(tmpdir)
            
            # 创建测试文件
            article1 = {"source_url": "https://example1.com", "title": "test1"}
            article2 = {"source_url": "https://example2.com", "title": "test2"}
            
            with open(articles_dir / "article1.json", "w") as f:
                json.dump(article1, f)
            with open(articles_dir / "article2.json", "w") as f:
                json.dump(article2, f)
            
            urls = get_existing_urls(articles_dir)
            
            assert len(urls) == 2
            assert "https://example1.com" in urls
            assert "https://example2.com" in urls
    
    def test_get_existing_urls_empty(self):
        """测试获取空目录的 URL"""
        with tempfile.TemporaryDirectory() as tmpdir:
            articles_dir = Path(tmpdir)
            urls = get_existing_urls(articles_dir)
            assert len(urls) == 0


class TestCheckDuplicate:
    """测试检查重复"""
    
    def test_check_duplicate_not_exists(self):
        """测试检查不存在的条目"""
        entry = {"url": "https://example.com"}
        existing_urls = set()
        
        result = check_duplicate(entry, existing_urls)
        assert result is False
    
    def test_check_duplicate_exists(self):
        """测试检查已存在的条目"""
        entry = {"url": "https://example.com"}
        existing_urls = {"https://example.com"}
        
        result = check_duplicate(entry, existing_urls)
        assert result is True
    
    def test_check_duplicate_no_url(self):
        """测试检查没有 URL 的条目"""
        entry = {"title": "test"}
        existing_urls = set()
        
        result = check_duplicate(entry, existing_urls)
        assert result is False


class TestFormatArticle:
    """测试格式化文章"""
    
    def test_format_article(self):
        """测试格式化文章"""
        entry = {
            "title": "Test Project",
            "url": "https://example.com",
            "source": "github",
            "popularity": 100,
            "summary": "A test project",
            "tags": ["llm", "agent"],
            "tech_direction": "llm",
            "quality_level": "A",
            "use_case": "开发者可以用这个工具"
        }
        
        article = format_article(entry)
        
        assert "id" in article
        assert article["title"] == "Test Project"
        assert article["source_url"] == "https://example.com"
        assert article["source_type"] == "github"
        assert article["summary"] == "A test project"
        assert article["tags"] == ["llm", "agent"]
        assert article["tech_direction"] == "llm"
        assert article["quality_level"] == "A"
        assert article["use_case"] == "开发者可以用这个工具"
        assert article["status"] == "analyzed"
        assert "collected_at" in article


class TestGenerateFilename:
    """测试生成文件名"""
    
    def test_generate_filename_github(self):
        """测试生成 GitHub 文件名"""
        article = {
            "source_type": "github",
            "title": "LLM Project"
        }
        
        filename = generate_filename(article, "2026-05-21")
        
        assert filename == "2026-05-21-github-llm-project.json"
    
    def test_generate_filename_hackernews(self):
        """测试生成 Hacker News 文件名"""
        article = {
            "source_type": "hackernews",
            "title": "AI Agent"
        }
        
        filename = generate_filename(article, "2026-05-21")
        
        assert filename == "2026-05-21-hackernews-ai-agent.json"
    
    def test_generate_filename_no_title(self):
        """测试没有标题的文件名"""
        article = {
            "source_type": "github",
            "title": ""
        }
        
        filename = generate_filename(article, "2026-05-21")
        
        assert filename == "2026-05-21-github-unknown.json"


class TestSaveArticle:
    """测试保存文章"""
    
    def test_save_article_success(self):
        """测试成功保存文章"""
        article = {
            "id": "test-id",
            "title": "Test Project",
            "source_url": "https://example.com",
            "source_type": "github",
            "summary": "A test project",
            "tags": ["llm"],
            "tech_direction": "llm",
            "quality_level": "A",
            "use_case": "开发者可以用这个工具",
            "status": "analyzed",
            "collected_at": "2026-05-21T08:00:00Z"
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            result = save_article(article, output_dir, "2026-05-21")
            
            assert result is True
            
            # 检查文件是否创建
            files = list(output_dir.glob("*.json"))
            assert len(files) == 1
            
            # 检查文件内容
            with open(files[0], "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                assert saved_data["title"] == "Test Project"


class TestOrganizeData:
    """测试整理数据"""
    
    def test_organize_data_success(self):
        """测试成功整理数据"""
        data = [
            {
                "title": "Test Project",
                "url": "https://example.com",
                "source": "github",
                "popularity": 100,
                "summary": "A test project",
                "tags": ["llm"],
                "tech_direction": "llm",
                "quality_level": "A",
                "use_case": "开发者可以用这个工具"
            }
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建输入文件
            input_file = Path(tmpdir) / "input.json"
            with open(input_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            
            # 创建输出目录
            output_dir = Path(tmpdir) / "articles"
            
            result = organize_data(input_file, output_dir)
            
            assert result is True
            
            # 检查文件是否创建
            files = list(output_dir.glob("*.json"))
            assert len(files) == 1
    
    def test_organize_data_duplicate(self):
        """测试整理重复数据"""
        data = [
            {
                "title": "Test Project",
                "url": "https://example.com",
                "source": "github",
                "popularity": 100,
                "summary": "A test project",
                "tags": ["llm"],
                "tech_direction": "llm",
                "quality_level": "A",
                "use_case": "开发者可以用这个工具"
            }
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建输入文件
            input_file = Path(tmpdir) / "input.json"
            with open(input_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            
            # 创建输出目录和已存在的文章
            output_dir = Path(tmpdir) / "articles"
            output_dir.mkdir()
            
            existing_article = {"source_url": "https://example.com", "title": "Test Project"}
            with open(output_dir / "existing.json", "w", encoding="utf-8") as f:
                json.dump(existing_article, f)
            
            result = organize_data(input_file, output_dir)
            
            assert result is False
            
            # 检查文件数量没有增加
            files = list(output_dir.glob("*.json"))
            assert len(files) == 1
    
    def test_organize_data_empty(self):
        """测试整理空数据"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建输入文件
            input_file = Path(tmpdir) / "input.json"
            with open(input_file, "w", encoding="utf-8") as f:
                json.dump([], f)
            
            # 创建输出目录
            output_dir = Path(tmpdir) / "articles"
            
            result = organize_data(input_file, output_dir)
            
            assert result is False
