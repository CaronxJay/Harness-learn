"""RSS 数据源加载器

用于加载和解析 pipeline/rss_sources.yaml 配置文件。

使用方法：
    from pipeline.rss_loader import load_rss_sources, get_enabled_sources

    # 加载所有数据源
    sources = load_rss_sources()

    # 获取启用的数据源
    enabled_sources = get_enabled_sources()

    # 按分类获取数据源
    ai_sources = get_sources_by_category("AI 研究")

编码规范：
    - 遵循 PEP 8
    - Google 风格 docstring
    - 使用 logging 不用 print
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    raise ImportError("缺少 PyYAML 库，请运行: pip install pyyaml")

# 配置日志
logger = logging.getLogger(__name__)

# 配置文件路径
RSS_SOURCES_FILE: Path = Path(__file__).parent / "rss_sources.yaml"


@dataclass
class RSSSource:
    """RSS 数据源"""
    name: str
    url: str
    category: str
    enabled: bool = True

    def __str__(self) -> str:
        """返回数据源描述"""
        status = "✓" if self.enabled else "✗"
        return f"[{status}] {self.name} ({self.category})"


def load_rss_sources(config_file: Optional[Path] = None) -> list[RSSSource]:
    """加载 RSS 数据源配置

    Args:
        config_file: 配置文件路径，默认使用 pipeline/rss_sources.yaml

    Returns:
        RSSSource 列表

    Raises:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: YAML 解析错误
    """
    if config_file is None:
        config_file = RSS_SOURCES_FILE

    if not config_file.exists():
        logger.error(f"配置文件不存在: {config_file}")
        raise FileNotFoundError(f"配置文件不存在: {config_file}")

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"YAML 解析错误: {e}")
        raise

    sources = []
    for item in data.get("sources", []):
        source = RSSSource(
            name=item.get("name", ""),
            url=item.get("url", ""),
            category=item.get("category", ""),
            enabled=item.get("enabled", True),
        )
        sources.append(source)

    logger.info(f"加载了 {len(sources)} 个 RSS 数据源")
    return sources


def get_enabled_sources(config_file: Optional[Path] = None) -> list[RSSSource]:
    """获取启用的数据源

    Args:
        config_file: 配置文件路径，默认使用 pipeline/rss_sources.yaml

    Returns:
        启用的 RSSSource 列表
    """
    sources = load_rss_sources(config_file)
    enabled = [s for s in sources if s.enabled]
    logger.info(f"启用的数据源: {len(enabled)}/{len(sources)}")
    return enabled


def get_sources_by_category(
    category: str,
    config_file: Optional[Path] = None,
) -> list[RSSSource]:
    """按分类获取数据源

    Args:
        category: 分类名称
        config_file: 配置文件路径，默认使用 pipeline/rss_sources.yaml

    Returns:
        指定分类的 RSSSource 列表
    """
    sources = load_rss_sources(config_file)
    filtered = [s for s in sources if s.category == category]
    logger.info(f"分类 '{category}' 的数据源: {len(filtered)}")
    return filtered


def get_all_categories(config_file: Optional[Path] = None) -> list[str]:
    """获取所有分类

    Args:
        config_file: 配置文件路径，默认使用 pipeline/rss_sources.yaml

    Returns:
        分类名称列表
    """
    sources = load_rss_sources(config_file)
    categories = list(set(s.category for s in sources))
    categories.sort()
    return categories


def print_sources_summary(config_file: Optional[Path] = None) -> None:
    """打印数据源摘要

    Args:
        config_file: 配置文件路径，默认使用 pipeline/rss_sources.yaml
    """
    sources = load_rss_sources(config_file)
    enabled_count = sum(1 for s in sources if s.enabled)

    logger.info("=" * 60)
    logger.info("RSS 数据源摘要")
    logger.info("=" * 60)
    logger.info(f"总计: {len(sources)} 个数据源")
    logger.info(f"启用: {enabled_count} 个")
    logger.info(f"禁用: {len(sources) - enabled_count} 个")
    logger.info("-" * 60)

    # 按分类显示
    categories = get_all_categories(config_file)
    for category in categories:
        category_sources = get_sources_by_category(category, config_file)
        enabled_in_category = sum(1 for s in category_sources if s.enabled)
        logger.info(f"\n{category} ({enabled_in_category}/{len(category_sources)} 启用):")
        for source in category_sources:
            logger.info(f"  {source}")


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger.info("=" * 60)
    logger.info("RSS 数据源加载器测试")
    logger.info("=" * 60)

    try:
        # 打印数据源摘要
        print_sources_summary()

        # 获取启用的数据源
        logger.info("\n--- 启用的数据源 ---")
        enabled_sources = get_enabled_sources()
        for source in enabled_sources:
            logger.info(f"  {source.name}: {source.url}")

        # 获取所有分类
        logger.info("\n--- 所有分类 ---")
        categories = get_all_categories()
        for category in categories:
            logger.info(f"  {category}")

    except FileNotFoundError as e:
        logger.error(f"文件未找到: {e}")
    except Exception as e:
        logger.error(f"加载失败: {e}")
