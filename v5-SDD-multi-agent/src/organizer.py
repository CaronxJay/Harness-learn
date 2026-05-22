"""整理 Agent - 去重检查、格式化为标准 JSON、分类存档"""

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_analyzed_data(file_path: Path) -> list[dict[str, Any]]:
    """加载已标注的数据
    
    Args:
        file_path: 数据文件路径
        
    Returns:
        数据列表
    """
    if not file_path.exists():
        logger.warning(f"文件不存在: {file_path}")
        return []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                logger.error(f"数据格式错误: {file_path} 不是数组")
                return []
            return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析错误: {file_path} - {e}")
        return []


def get_existing_urls(articles_dir: Path) -> set[str]:
    """获取已存在的文章 URL
    
    Args:
        articles_dir: 文章目录
        
    Returns:
        URL 集合
    """
    urls = set()
    
    if not articles_dir.exists():
        return urls
    
    for file_path in articles_dir.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "source_url" in data:
                    urls.add(data["source_url"])
        except Exception as e:
            logger.warning(f"读取文件失败: {file_path} - {e}")
            continue
    
    return urls


def check_duplicate(entry: dict[str, Any], existing_urls: set[str]) -> bool:
    """检查是否重复
    
    Args:
        entry: 数据条目
        existing_urls: 已存在的 URL 集合
        
    Returns:
        是否重复
    """
    url = entry.get("url", "")
    if not url:
        logger.warning("条目缺少 URL 字段")
        return False
    
    return url in existing_urls


def format_article(entry: dict[str, Any]) -> dict[str, Any]:
    """格式化为标准 JSON
    
    Args:
        entry: 原始数据条目
        
    Returns:
        格式化后的文章
    """
    # 生成 UUID
    article_id = str(uuid.uuid4())
    
    # 获取当前时间
    collected_at = datetime.now().isoformat()
    
    # 提取字段
    title = entry.get("title", "")
    source_url = entry.get("url", "")
    source_type = entry.get("source", "github")
    summary = entry.get("summary", "")
    tags = entry.get("tags", [])
    tech_direction = entry.get("tech_direction", "unknown")
    quality_level = entry.get("quality_level", "C")
    use_case = entry.get("use_case", "未知")
    
    # 构建文章
    article = {
        "id": article_id,
        "title": title,
        "source_url": source_url,
        "source_type": source_type,
        "summary": summary,
        "tags": tags,
        "tech_direction": tech_direction,
        "quality_level": quality_level,
        "use_case": use_case,
        "status": "analyzed",
        "collected_at": collected_at
    }
    
    return article


def generate_filename(article: dict[str, Any], date_str: str) -> str:
    """生成文件名
    
    Args:
        article: 文章数据
        date_str: 日期字符串
        
    Returns:
        文件名
    """
    source = article.get("source_type", "github")
    title = article.get("title", "")
    
    # 生成 slug
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    slug = slug.strip("-")
    if not slug:
        slug = "unknown"
    
    return f"{date_str}-{source}-{slug}.json"


def save_article(article: dict[str, Any], output_dir: Path, date_str: str) -> bool:
    """保存文章
    
    Args:
        article: 文章数据
        output_dir: 输出目录
        date_str: 日期字符串
        
    Returns:
        是否保存成功
    """
    # 确保目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成文件名
    filename = generate_filename(article, date_str)
    output_file = output_dir / filename
    
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)
        logger.info(f"文章已保存到: {output_file}")
        return True
    except Exception as e:
        logger.error(f"保存文章失败: {e}")
        return False


def organize_data(input_file: Path, output_dir: Path) -> bool:
    """整理数据
    
    Args:
        input_file: 输入文件路径
        output_dir: 输出目录
        
    Returns:
        是否整理成功
    """
    # 加载数据
    data = load_analyzed_data(input_file)
    if not data:
        logger.warning(f"没有数据需要整理: {input_file}")
        return False
    
    logger.info(f"开始整理 {len(data)} 条数据")
    
    # 获取已存在的 URL
    existing_urls = get_existing_urls(output_dir)
    
    # 获取日期字符串
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for entry in data:
        # 检查是否重复
        if check_duplicate(entry, existing_urls):
            logger.info(f"跳过重复条目: {entry.get('title', '未知')}")
            skip_count += 1
            continue
        
        # 格式化文章
        article = format_article(entry)
        
        # 保存文章
        if save_article(article, output_dir, date_str):
            success_count += 1
            existing_urls.add(entry.get("url", ""))
        else:
            fail_count += 1
    
    logger.info(f"整理完成: 成功 {success_count} 条, 跳过 {skip_count} 条, 失败 {fail_count} 条")
    return success_count > 0


def main():
    """主函数"""
    logger.info("开始整理数据")
    
    # 配置路径
    input_dir = Path("knowledge/raw")
    output_dir = Path("knowledge/articles")
    
    # 获取最新的数据文件
    input_files = sorted(input_dir.glob("*.json"), reverse=True)
    if not input_files:
        logger.error("没有找到数据文件")
        return
    
    input_file = input_files[0]
    logger.info(f"使用数据文件: {input_file}")
    
    # 整理数据
    success = organize_data(input_file, output_dir)
    
    if success:
        logger.info("数据整理完成")
    else:
        logger.error("数据整理失败")


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    main()
