"""四步知识库自动化流水线

采集 → 分析 → 整理 → 保存，支持 GitHub Search API 和 RSS 数据源。

使用方法：
    # 完整流水线
    python pipeline/pipeline.py --sources github,rss --limit 20

    # 只采集 GitHub
    python pipeline/pipeline.py --sources github --limit 5

    # 只采集 RSS
    python pipeline/pipeline.py --sources rss --limit 10

    # 干跑模式（不调用 LLM，不保存文件）
    python pipeline/pipeline.py --sources github --limit 5 --dry-run

    # 详细日志
    python pipeline/pipeline.py --verbose

编码规范：
    - 遵循 PEP 8
    - Google 风格 docstring
    - 使用 logging 不用 print
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import httpx
except ImportError:
    print("缺少 httpx 库，请运行: pip install httpx")
    sys.exit(1)

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 支持直接运行和作为模块导入
try:
    from pipeline.model_client import chat_with_retry, create_provider
except ImportError:
    from model_client import chat_with_retry, create_provider

# 配置日志
logger = logging.getLogger(__name__)

# 目录配置
RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"

# GitHub API 配置
GITHUB_API_BASE = "https://api.github.com"
GITHUB_SEARCH_QUERIES = [
    "LLM framework",
    "AI agent",
    "RAG retrieval",
    "language model tools",
]


# ============================================================
# 数据结构
# ============================================================

@dataclass
class RawItem:
    """原始采集数据"""
    title: str
    url: str
    source_type: str  # "github" | "rss"
    description: str = ""
    stars: int = 0
    language: str = ""
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "title": self.title,
            "url": self.url,
            "source_type": self.source_type,
            "description": self.description,
            "stars": self.stars,
            "language": self.language,
            "collected_at": self.collected_at,
        }


@dataclass
class AnalysisResult:
    """LLM 分析结果"""
    summary: str
    tags: list[str]
    tech_direction: str
    quality_level: str  # "A" | "B" | "C"
    use_case: str

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "summary": self.summary,
            "tags": self.tags,
            "tech_direction": self.tech_direction,
            "quality_level": self.quality_level,
            "use_case": self.use_case,
        }


@dataclass
class KnowledgeEntry:
    """知识条目"""
    id: str
    title: str
    source_url: str
    source_type: str
    summary: str
    tags: list[str]
    tech_direction: str
    quality_level: str
    use_case: str
    status: str = "analyzed"
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "summary": self.summary,
            "tags": self.tags,
            "tech_direction": self.tech_direction,
            "quality_level": self.quality_level,
            "use_case": self.use_case,
            "status": self.status,
            "collected_at": self.collected_at,
        }


# ============================================================
# Step 1: 采集（Collect）
# ============================================================

def collect_github(limit: int = 10) -> list[RawItem]:
    """从 GitHub Search API 采集 AI 相关项目

    Args:
        limit: 最大采集数量

    Returns:
        RawItem 列表
    """
    items: list[RawItem] = []
    seen_urls: set[str] = set()

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Knowledge-Base-Pipeline",
    }

    # 如果配置了 GitHub Token，添加到请求头
    import os
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    with httpx.Client(timeout=30.0, headers=headers) as client:
        for query in GITHUB_SEARCH_QUERIES:
            if len(items) >= limit:
                break

            logger.info(f"GitHub 搜索: {query}")
            params = {
                "q": f"{query} language:python",
                "sort": "stars",
                "order": "desc",
                "per_page": min(limit - len(items), 10),
            }

            try:
                response = client.get(f"{GITHUB_API_BASE}/search/repositories", params=params)
                response.raise_for_status()
                data = response.json()

                for repo in data.get("items", []):
                    url = repo.get("html_url", "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    item = RawItem(
                        title=repo.get("full_name", ""),
                        url=url,
                        source_type="github",
                        description=repo.get("description", "") or "",
                        stars=repo.get("stargazers_count", 0),
                        language=repo.get("language", "") or "",
                    )
                    items.append(item)

                    if len(items) >= limit:
                        break

            except httpx.HTTPStatusError as e:
                logger.warning(f"GitHub API 请求失败: {e.response.status_code}")
            except Exception as e:
                logger.error(f"GitHub 采集异常: {e}")

    logger.info(f"GitHub 采集完成: {len(items)} 个项目")
    return items[:limit]


def collect_rss(limit: int = 10) -> list[RawItem]:
    """从 RSS 源采集 AI 相关内容

    Args:
        limit: 最大采集数量

    Returns:
        RawItem 列表
    """
    # 支持直接运行和作为模块导入
    try:
        from pipeline.rss_loader import get_enabled_sources
    except ImportError:
        from rss_loader import get_enabled_sources

    items: list[RawItem] = []
    seen_urls: set[str] = set()

    sources = get_enabled_sources()
    logger.info(f"启用的 RSS 源: {len(sources)} 个")

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for source in sources:
            if len(items) >= limit:
                break

            logger.info(f"RSS 采集: {source.name}")
            try:
                response = client.get(source.url)
                response.raise_for_status()
                content = response.text

                # 简易正则解析 RSS
                entries = _parse_rss_entries(content)

                for entry in entries:
                    if len(items) >= limit:
                        break

                    url = entry.get("link", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    item = RawItem(
                        title=entry.get("title", "无标题"),
                        url=url,
                        source_type="rss",
                        description=entry.get("description", ""),
                    )
                    items.append(item)

            except httpx.HTTPStatusError as e:
                logger.warning(f"RSS 请求失败 [{source.name}]: {e.response.status_code}")
            except Exception as e:
                logger.error(f"RSS 采集异常 [{source.name}]: {e}")

    logger.info(f"RSS 采集完成: {len(items)} 条内容")
    return items[:limit]


def _parse_rss_entries(xml_content: str) -> list[dict[str, str]]:
    """简易正则解析 RSS XML

    Args:
        xml_content: RSS XML 内容

    Returns:
        解析后的条目列表
    """
    entries = []

    # 匹配 <item> 或 <entry> 标签
    item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
    entry_pattern = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)

    items = item_pattern.findall(xml_content) or entry_pattern.findall(xml_content)

    for item_xml in items:
        entry = {}

        # 提取 title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", item_xml, re.DOTALL)
        if title_match:
            entry["title"] = _clean_xml_text(title_match.group(1))

        # 提取 link
        link_match = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', item_xml)
        if not link_match:
            link_match = re.search(r"<link[^>]*>(.*?)</link>", item_xml, re.DOTALL)
        if link_match:
            entry["link"] = _clean_xml_text(link_match.group(1))

        # 提取 description / summary
        desc_match = re.search(r"<description[^>]*>(.*?)</description>", item_xml, re.DOTALL)
        if not desc_match:
            desc_match = re.search(r"<summary[^>]*>(.*?)</summary>", item_xml, re.DOTALL)
        if desc_match:
            entry["description"] = _clean_xml_text(desc_match.group(1))[:500]

        if entry.get("title") and entry.get("link"):
            entries.append(entry)

    return entries


def _clean_xml_text(text: str) -> str:
    """清理 XML 文本

    Args:
        text: 原始 XML 文本

    Returns:
        清理后的文本
    """
    # 移除 CDATA 标记
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    # 移除 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    # 解码 HTML 实体
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&nbsp;", " ")
    # 清理空白
    text = re.sub(r"\s+", " ", text).strip()
    return text


def collect(sources: list[str], limit: int = 10) -> list[RawItem]:
    """执行采集步骤

    Args:
        sources: 数据源列表，如 ["github", "rss"]
        limit: 每个源的最大采集数量

    Returns:
        RawItem 列表
    """
    all_items: list[RawItem] = []

    if "github" in sources:
        github_items = collect_github(limit)
        all_items.extend(github_items)

    if "rss" in sources:
        rss_items = collect_rss(limit)
        all_items.extend(rss_items)

    logger.info(f"采集总计: {len(all_items)} 条内容")
    return all_items


# ============================================================
# Step 2: 分析（Analyze）
# ============================================================

ANALYSIS_PROMPT = """你是一个 AI 技术分析师。请分析以下项目/文章，返回 JSON 格式的分析结果。

项目信息：
- 标题：{title}
- 链接：{url}
- 描述：{description}
- 来源：{source_type}

请返回以下 JSON 格式（不要有其他内容）：
{{
    "summary": "50-100字的中文摘要",
    "tags": ["标签1", "标签2", "标签3"],
    "tech_direction": "技术方向（如 llm/agent/rag/cv/nlp 等）",
    "quality_level": "质量等级（A/B/C，A最高）",
    "use_case": "适用场景描述"
}}"""


def analyze_item(item: RawItem, provider=None) -> Optional[AnalysisResult]:
    """分析单个采集项

    Args:
        item: 原始采集数据
        provider: LLM 提供商实例

    Returns:
        AnalysisResult 或 None（分析失败时）
    """
    prompt = ANALYSIS_PROMPT.format(
        title=item.title,
        url=item.url,
        description=item.description[:300] if item.description else "无",
        source_type=item.source_type,
    )

    try:
        response = chat_with_retry(
            prompt=prompt,
            system_prompt="你是一个 JSON 输出助手，只返回有效的 JSON。",
            temperature=0.3,
            max_tokens=500,
            provider=provider,
        )

        # 解析 JSON 响应
        content = response.content.strip()
        # 尝试提取 JSON 块
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = json.loads(content)

        return AnalysisResult(
            summary=data.get("summary", ""),
            tags=data.get("tags", []),
            tech_direction=data.get("tech_direction", "unknown"),
            quality_level=data.get("quality_level", "C"),
            use_case=data.get("use_case", ""),
        )

    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败 [{item.title}]: {e}")
        return None
    except Exception as e:
        logger.warning(f"分析失败 [{item.title}]: {e}")
        return None


def analyze(items: list[RawItem], dry_run: bool = False) -> list[tuple[RawItem, Optional[AnalysisResult]]]:
    """执行分析步骤

    Args:
        items: 原始采集数据列表
        dry_run: 干跑模式，不调用 LLM

    Returns:
        (RawItem, AnalysisResult) 元组列表
    """
    if dry_run:
        logger.info("干跑模式：跳过 LLM 分析")
        return [(item, None) for item in items]

    # 创建 LLM 提供商
    try:
        provider = create_provider()
        logger.info(f"使用 LLM 提供商: {provider.get_provider_name()}")
    except ValueError as e:
        logger.error(f"无法创建 LLM 提供商: {e}")
        return [(item, None) for item in items]

    results: list[tuple[RawItem, Optional[AnalysisResult]]] = []
    total = len(items)

    for i, item in enumerate(items, 1):
        logger.info(f"分析进度: {i}/{total} - {item.title[:50]}")
        result = analyze_item(item, provider)
        results.append((item, result))

    success_count = sum(1 for _, r in results if r is not None)
    logger.info(f"分析完成: {success_count}/{total} 成功")
    return results


# ============================================================
# Step 3: 整理（Organize）
# ============================================================

def generate_id(url: str) -> str:
    """根据 URL 生成唯一 ID

    Args:
        url: 来源链接

    Returns:
        UUID 格式的 ID
    """
    hash_digest = hashlib.md5(url.encode()).hexdigest()[:12]
    return str(uuid.UUID(hex=hash_digest + "0" * 20))


def organize(
    analyzed_items: list[tuple[RawItem, Optional[AnalysisResult]]],
) -> list[KnowledgeEntry]:
    """整理分析结果：去重 + 格式标准化 + 校验

    Args:
        analyzed_items: (RawItem, AnalysisResult) 元组列表

    Returns:
        KnowledgeEntry 列表
    """
    entries: list[KnowledgeEntry] = []
    seen_urls: set[str] = set()

    for raw_item, analysis in analyzed_items:
        # 去重
        if raw_item.url in seen_urls:
            logger.debug(f"跳过重复: {raw_item.url}")
            continue
        seen_urls.add(raw_item.url)

        # 如果分析失败，使用默认值
        if analysis is None:
            analysis = AnalysisResult(
                summary=raw_item.description[:100] if raw_item.description else "暂无摘要",
                tags=["未分类"],
                tech_direction="unknown",
                quality_level="C",
                use_case="待分析",
            )

        # 格式标准化
        entry = KnowledgeEntry(
            id=generate_id(raw_item.url),
            title=raw_item.title,
            source_url=raw_item.url,
            source_type=raw_item.source_type,
            summary=analysis.summary,
            tags=analysis.tags,
            tech_direction=analysis.tech_direction,
            quality_level=analysis.quality_level,
            use_case=analysis.use_case,
            status="analyzed",
            collected_at=raw_item.collected_at,
        )

        # 校验
        if _validate_entry(entry):
            entries.append(entry)

    logger.info(f"整理完成: {len(entries)} 条知识条目")
    return entries


def _validate_entry(entry: KnowledgeEntry) -> bool:
    """校验知识条目

    Args:
        entry: 知识条目

    Returns:
        是否有效
    """
    if not entry.title:
        logger.warning(f"条目缺少标题: {entry.source_url}")
        return False

    if not entry.source_url:
        logger.warning(f"条目缺少链接: {entry.title}")
        return False

    if entry.quality_level not in ("A", "B", "C"):
        logger.warning(f"无效的质量等级: {entry.quality_level}")
        entry.quality_level = "C"

    return True


# ============================================================
# Step 4: 保存（Save）
# ============================================================

def save_raw(items: list[RawItem], dry_run: bool = False) -> list[Path]:
    """保存原始采集数据到 knowledge/raw/

    Args:
        items: 原始采集数据列表
        dry_run: 干跑模式，不实际保存

    Returns:
        保存的文件路径列表
    """
    if dry_run:
        logger.info(f"干跑模式：跳过保存原始数据 ({len(items)} 条)")
        return []

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_paths: list[Path] = []

    # 按来源分组保存
    github_items = [i for i in items if i.source_type == "github"]
    rss_items = [i for i in items if i.source_type == "rss"]

    if github_items:
        path = RAW_DIR / f"github_{timestamp}.json"
        data = [item.to_dict() for item in github_items]
        _save_json(path, data)
        saved_paths.append(path)

    if rss_items:
        path = RAW_DIR / f"rss_{timestamp}.json"
        data = [item.to_dict() for item in rss_items]
        _save_json(path, data)
        saved_paths.append(path)

    logger.info(f"原始数据已保存: {len(saved_paths)} 个文件")
    return saved_paths


def save_articles(entries: list[KnowledgeEntry], dry_run: bool = False) -> list[Path]:
    """保存知识条目到 knowledge/articles/

    Args:
        entries: 知识条目列表
        dry_run: 干跑模式，不实际保存

    Returns:
        保存的文件路径列表
    """
    if dry_run:
        logger.info(f"干跑模式：跳过保存文章 ({len(entries)} 条)")
        # 干跑模式下打印预览
        for entry in entries[:3]:
            logger.info(f"  预览: {entry.title}")
            logger.info(f"    摘要: {entry.summary[:80]}...")
            logger.info(f"    标签: {entry.tags}")
        return []

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []

    for entry in entries:
        # 文件名：{id}.json
        filename = f"{entry.id}.json"
        path = ARTICLES_DIR / filename

        # 如果文件已存在，跳过
        if path.exists():
            logger.debug(f"文件已存在，跳过: {filename}")
            continue

        _save_json(path, entry.to_dict())
        saved_paths.append(path)

    logger.info(f"文章已保存: {len(saved_paths)} 个文件")
    return saved_paths


def _save_json(path: Path, data: Any) -> None:
    """保存 JSON 文件

    Args:
        path: 文件路径
        data: 要保存的数据
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.debug(f"已保存: {path}")


# ============================================================
# 流水线主函数
# ============================================================

def run_pipeline(
    sources: list[str],
    limit: int = 10,
    dry_run: bool = False,
) -> dict[str, Any]:
    """执行完整流水线

    Args:
        sources: 数据源列表，如 ["github", "rss"]
        limit: 每个源的最大采集数量
        dry_run: 干跑模式

    Returns:
        执行结果统计
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("知识库自动化流水线启动")
    logger.info(f"数据源: {sources}")
    logger.info(f"采集限制: {limit}")
    logger.info(f"干跑模式: {dry_run}")
    logger.info("=" * 60)

    # Step 1: 采集
    logger.info("\n[Step 1/4] 采集（Collect）")
    raw_items = collect(sources, limit)

    if not raw_items:
        logger.warning("未采集到任何内容，流水线结束")
        return {
            "collected": 0,
            "analyzed": 0,
            "saved": 0,
            "duration_seconds": 0,
        }

    # 保存原始数据
    save_raw(raw_items, dry_run)

    # Step 2: 分析
    logger.info("\n[Step 2/4] 分析（Analyze）")
    analyzed_items = analyze(raw_items, dry_run)

    # Step 3: 整理
    logger.info("\n[Step 3/4] 整理（Organize）")
    entries = organize(analyzed_items)

    # Step 4: 保存
    logger.info("\n[Step 4/4] 保存（Save）")
    saved_paths = save_articles(entries, dry_run)

    # 统计
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    result = {
        "collected": len(raw_items),
        "analyzed": sum(1 for _, r in analyzed_items if r is not None),
        "organized": len(entries),
        "saved": len(saved_paths),
        "duration_seconds": round(duration, 2),
    }

    logger.info("\n" + "=" * 60)
    logger.info("流水线执行完成")
    logger.info(f"采集: {result['collected']} 条")
    logger.info(f"分析: {result['analyzed']} 条")
    logger.info(f"整理: {result['organized']} 条")
    logger.info(f"保存: {result['saved']} 个文件")
    logger.info(f"耗时: {result['duration_seconds']} 秒")
    logger.info("=" * 60)

    return result


# ============================================================
# CLI 入口
# ============================================================

def parse_args() -> argparse.Namespace:
    """解析命令行参数

    Returns:
        解析后的参数
    """
    parser = argparse.ArgumentParser(
        description="知识库自动化流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python pipeline/pipeline.py --sources github,rss --limit 20
  python pipeline/pipeline.py --sources github --limit 5 --dry-run
  python pipeline/pipeline.py --verbose
        """,
    )

    parser.add_argument(
        "--sources",
        type=str,
        default="github,rss",
        help="数据源，逗号分隔 (default: github,rss)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="每个源的最大采集数量 (default: 10)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式：不调用 LLM，不保存文件",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细日志输出",
    )

    return parser.parse_args()


def main() -> None:
    """主函数"""
    args = parse_args()

    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 解析数据源
    sources = [s.strip().lower() for s in args.sources.split(",")]
    valid_sources = ["github", "rss"]
    for source in sources:
        if source not in valid_sources:
            logger.error(f"无效的数据源: {source}，支持: {valid_sources}")
            sys.exit(1)

    # 执行流水线
    try:
        result = run_pipeline(
            sources=sources,
            limit=args.limit,
            dry_run=args.dry_run,
        )

        # 输出 JSON 结果
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except KeyboardInterrupt:
        logger.info("用户中断，流水线停止")
        sys.exit(0)
    except Exception as e:
        logger.error(f"流水线执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
