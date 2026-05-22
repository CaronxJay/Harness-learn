#!/usr/bin/env python3
"""知识库自动化流水线。

四步流程：采集 → 分析 → 整理 → 保存
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx

from model_client import create_provider, chat_with_retry

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

TZ = timezone(timedelta(hours=8))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"

RSS_FEEDS: dict[str, str] = {
    "arxiv_cs_ai": "https://export.arxiv.org/rss/cs.AI",
    "arxiv_cs_cl": "https://export.arxiv.org/rss/cs.CL",
}

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_SEARCH_QUERY = "ai+llm+agent+machine+learning+deep+learning"
GITHUB_SORT = "stars"
GITHUB_ORDER = "desc"

VALID_CATEGORIES: frozenset[str] = frozenset({
    "agent-framework",
    "llm",
    "research",
    "application",
    "infrastructure",
    "benchmark",
    "security",
    "multimodal",
})

VALID_STATUSES: frozenset[str] = frozenset({"draft", "published", "archived"})

ANALYSIS_SYSTEM_PROMPT = """\
You are an AI content analyst specializing in AI, LLM, and Agent research.
Analyze the provided content and return ONLY a valid JSON object (no markdown,
no explanation, no code fences). The JSON must contain exactly these fields:

- title: Short descriptive title in Chinese. If the original content is in
  English, translate it into concise Chinese.
- summary: Chinese summary, max 200 characters. Capture the core contribution
  or value proposition.
- summary_en: English summary, max 200 characters. Only fill this if the
  original content language is English; otherwise set to null.
- tags: Array of 2-5 relevant lowercase tags selected from:
  agent-framework, llm, research, application, infrastructure, benchmark,
  security, multimodal, open-source, python, javascript, rust, golang, tool,
  rag, fine-tuning, prompt-engineering, evaluation
- category: Exactly one of: agent-framework, llm, research, application,
  infrastructure, benchmark, security, multimodal
- relevance_score: Float 0.0-1.0. How relevant is this to the AI/LLM/Agent
  field? 1.0 = directly about LLM/Agent, 0.5 = tangentially related,
  0.0 = unrelated.
- language: "zh" if the original content is primarily Chinese, otherwise "en".
"""

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。

    Args:
        argv: 命令行参数列表，为 None 时使用 sys.argv。

    Returns:
        解析后的 Namespace 对象。
    """
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="AI 知识库自动化流水线：采集 → 分析 → 整理 → 保存",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="github,rss",
        help='采集源，逗号分隔。可选: github, rss（默认: github,rss）',
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="总采集条目数上限（默认: 20）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式：执行采集和分析，但不写入文件",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出详细日志",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Step 1: 采集 (Collect)
# ---------------------------------------------------------------------------


def _parse_rss_xml(content: str) -> list[dict[str, str]]:
    """用简易正则解析 RSS XML，提取 item 列表。

    Args:
        content: RSS XML 原始文本。

    Returns:
        每项包含 title / link / description / pub_date 的字典列表。
    """
    items: list[dict[str, str]] = []
    item_blocks = re.findall(r"<item>(.*?)</item>", content, re.DOTALL)

    for block in item_blocks:
        title_m = re.search(r"<title>(.*?)</title>", block, re.DOTALL)
        link_m = re.search(r"<link>(.*?)</link>", block, re.DOTALL)
        desc_m = re.search(r"<description>(.*?)</description>", block, re.DOTALL)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.DOTALL)

        if not title_m or not link_m:
            continue

        title = _strip_html(title_m.group(1).strip())
        description = _strip_html(desc_m.group(1).strip()) if desc_m else ""
        items.append({
            "title": title,
            "url": link_m.group(1).strip(),
            "description": description,
            "pub_date": date_m.group(1).strip() if date_m else "",
        })

    return items


_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _strip_html(html: str) -> str:
    """移除 HTML 标签，解码常见实体。

    Args:
        html: 含 HTML 的文本。

    Returns:
        纯文本。
    """
    text = _HTML_TAG_RE.sub("", html)
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&").replace("&quot;", '"')
    text = text.replace("&#39;", "'").replace("&apos;", "'")
    return text.strip()


async def _collect_github(client: httpx.AsyncClient, limit: int) -> list[dict[str, Any]]:
    """从 GitHub Search API 采集 AI 相关仓库。

    Args:
        client: httpx 异步客户端。
        limit: 最大采集数。

    Returns:
        仓库信息字典列表。
    """
    params: dict[str, Any] = {
        "q": GITHUB_SEARCH_QUERY,
        "sort": GITHUB_SORT,
        "order": GITHUB_ORDER,
        "per_page": min(limit, 100),
    }
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    logger.info("GitHub Search API: %s?q=%s", GITHUB_SEARCH_URL, GITHUB_SEARCH_QUERY)

    try:
        response = await client.get(
            GITHUB_SEARCH_URL, params=params, headers=headers
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("GitHub API 请求失败 HTTP %s: %s", exc.response.status_code, exc)
        return []
    except httpx.RequestError as exc:
        logger.warning("GitHub API 网络错误: %s", exc)
        return []

    items = data.get("items", [])[:limit]
    return [
        {
            "title": repo.get("full_name", repo.get("name", "")),
            "url": repo.get("html_url", ""),
            "description": repo.get("description") or "",
            "stars": repo.get("stargazers_count", 0),
            "language": repo.get("language") or "",
            "topics": repo.get("topics", []),
        }
        for repo in items
    ]


async def _collect_rss(client: httpx.AsyncClient, limit: int) -> list[dict[str, Any]]:
    """从 arXiv RSS 源采集 AI 领域论文。

    Args:
        client: httpx 异步客户端。
        limit: 最大采集数。

    Returns:
        论文信息字典列表。
    """
    per_feed = max(1, limit // len(RSS_FEEDS))
    all_items: list[dict[str, Any]] = []

    for name, url in RSS_FEEDS.items():
        logger.info("RSS 采集 %s: %s", name, url)
        try:
            response = await client.get(url)
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("RSS 采集失败 %s: %s", name, exc)
            continue

        raw_items = _parse_rss_xml(response.text)[:per_feed]
        for item in raw_items:
            item["source_feed"] = name
        all_items.extend(raw_items)

    return all_items[:limit]


async def _do_collect(
    sources: list[str],
    limit: int,
) -> dict[str, list[dict[str, Any]]]:
    """执行采集步骤，分发到不同的采集器。

    Args:
        sources: 采集源列表（github / rss）。
        limit: 总采集条目数上限，按源数量均分。

    Returns:
        以 source 为 key、采集条目列表为 value 的字典。
    """
    per_source = max(1, limit // len(sources))
    result: dict[str, list[dict[str, Any]]] = {}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": "ai-knowledge-base/1.0"},
    ) as client:
        if "github" in sources:
            items = await _collect_github(client, per_source)
            for it in items:
                it["_source"] = "github"
            result["github"] = items
            logger.info("  GitHub Search: %d items collected", len(items))

        if "rss" in sources:
            items = await _collect_rss(client, per_source)
            for it in items:
                it["_source"] = "rss"
            result["rss"] = items
            logger.info("  RSS Feeds: %d items collected", len(items))

    return result


# ---------------------------------------------------------------------------
# Step 2: 分析 (Analyze)
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """从 LLM 回复中提取 JSON，处理 markdown 代码块包裹的情况。

    Args:
        text: LLM 原始回复。

    Returns:
        纯 JSON 文本。
    """
    text = text.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


async def _analyze_items(
    provider: Any,
    items: list[dict[str, Any]],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """调用 LLM 对采集条目进行分析（摘要/评分/标签）。

    Args:
        provider: LLM 提供商实例。
        items: 待分析的采集条目列表。
        dry_run: 是否为干跑模式。

    Returns:
        已附加分析结果的条目列表。
    """
    semaphore = asyncio.Semaphore(3) if not dry_run else asyncio.Semaphore(1)

    async def _analyze_one(idx: int, item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            prefix = f"[{idx + 1}/{len(items)}]"
            title = item.get("title", "")[:60]

            if dry_run:
                logger.info("  %s DRY-RUN %s... (skipped)", prefix, title)
                item["_analysis"] = {
                    "title": title,
                    "summary": f"[DRY-RUN] {item.get('description', '')[:100]}",
                    "summary_en": None,
                    "tags": ["dry-run"],
                    "category": "application",
                    "relevance_score": 0.8,
                    "language": "en",
                }
                return item

            messages: list[dict[str, str]] = [
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(item, ensure_ascii=False, default=str)},
            ]

            try:
                logger.debug("  %s 分析中: %s...", prefix, title)
                response = await chat_with_retry(provider, messages, temperature=0.3)
                json_str = _extract_json(response.content)
                analysis = json.loads(json_str)
                item["_analysis"] = analysis
                logger.info(
                    "  %s ✓ %s [score=%.2f]",
                    prefix,
                    title,
                    analysis.get("relevance_score", 0),
                )
            except Exception as exc:
                logger.warning("  %s ✗ %s: %s", prefix, title, exc)
                item["_analysis"] = {"_error": str(exc)}
            return item

    tasks = [_analyze_one(i, item) for i, item in enumerate(items)]
    results = await asyncio.gather(*tasks)
    return list(results)


async def _do_analyze(
    collected: dict[str, list[dict[str, Any]]],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """执行分析步骤。

    Args:
        collected: 按 source 分组的采集结果。
        dry_run: 是否为干跑模式。

    Returns:
        已附加分析结果的全部条目列表。

    Raises:
        ValueError: 非干跑模式且缺少 API Key 时抛出。
    """
    all_items: list[dict[str, Any]] = []
    for source, items in collected.items():
        all_items.extend(items)

    if not all_items:
        return []

    if dry_run:
        logger.info("  干跑模式：跳过 LLM 分析，使用模拟数据")
        return await _analyze_items(None, all_items, dry_run=True)

    logger.info("  初始化 LLM 客户端...")
    provider = create_provider()
    try:
        return await _analyze_items(provider, all_items, dry_run=False)
    finally:
        await provider.close()


# ---------------------------------------------------------------------------
# Step 3: 整理 (Organize)
# ---------------------------------------------------------------------------


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 URL 去重，保留星数更高或信息更全的条目。

    Args:
        items: 含分析结果的条目列表。

    Returns:
        去重后的条目列表。
    """
    seen: dict[str, dict[str, Any]] = {}
    for item in items:
        url = item.get("url", "")
        if not url:
            continue
        if url in seen:
            existing = seen[url]
            if item.get("stars", 0) > existing.get("stars", 0):
                seen[url] = item
        else:
            seen[url] = item
    return list(seen.values())


def _validate_item(item: dict[str, Any]) -> list[str]:
    """校验条目必需字段和格式，返回错误列表。

    Args:
        item: 待校验的条目。

    Returns:
        错误消息列表，为空表示通过。
    """
    analysis = item.get("_analysis", {})
    errors: list[str] = []

    if not item.get("title"):
        errors.append("missing title")
    if not item.get("url"):
        errors.append("missing url")

    ana_title = analysis.get("title")
    if ana_title is None:
        errors.append("analysis missing title")

    summary = analysis.get("summary")
    if not summary or not isinstance(summary, str) or len(summary) > 200:
        errors.append("analysis summary invalid or >200 chars")

    tags = analysis.get("tags")
    if not isinstance(tags, list) or len(tags) < 1:
        errors.append("tags must be non-empty array")

    category = analysis.get("category")
    if category not in VALID_CATEGORIES:
        errors.append(f"invalid category: {category}")

    score = analysis.get("relevance_score")
    if not isinstance(score, (int, float)) or not (0.0 <= float(score) <= 1.0):
        errors.append(f"relevance_score out of range: {score}")

    lang = analysis.get("language")
    if lang not in ("zh", "en"):
        errors.append(f"invalid language: {lang}")

    return errors


def _do_organize(
    analyzed: list[dict[str, Any]],
    source: str,
    start_idx: int = 1,
) -> list[dict[str, Any]]:
    """执行整理步骤：去重、过滤无效条目、格式标准化。

    Args:
        analyzed: 已分析的条目列表。
        source: 来源标识（github / rss）。

    Returns:
        格式标准化后的知识条目列表，按 relevance_score 降序排列。
    """
    before = len(analyzed)

    items = [it for it in analyzed if "_error" not in it.get("_analysis", {})]
    err_count = before - len(items)
    if err_count:
        logger.warning("  %d 条目分析失败，已剔除", err_count)

    items = _deduplicate(items)
    dup_count = len(analyzed) - len(items) - err_count
    if dup_count:
        logger.info("  %d 条目去重移除", max(0, dup_count))

    valid: list[dict[str, Any]] = []
    invalid_count = 0
    for item in items:
        errors = _validate_item(item)
        if errors:
            logger.debug("  条目校验失败 %s: %s", item.get("url", ""), errors)
            invalid_count += 1
            continue
        valid.append(item)

    if invalid_count:
        logger.warning("  %d 条目校验失败，已剔除", invalid_count)

    valid.sort(
        key=lambda it: it.get("_analysis", {}).get("relevance_score", 0),
        reverse=True,
    )

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    for idx, item in enumerate(valid, start_idx):
        analysis = item["_analysis"]
        item_id = f"{today}-{source}-{idx:03d}"
        article: dict[str, Any] = {
            "id": item_id,
            "title": analysis["title"],
            "source": f"{source}_trending",
            "source_url": item.get("url", ""),
            "language": analysis.get("language", "en"),
            "summary": analysis["summary"],
            "summary_en": analysis.get("summary_en"),
            "tags": analysis.get("tags", []),
            "category": analysis.get("category", "application"),
            "relevance_score": float(analysis.get("relevance_score", 0)),
            "status": "published",
            "created_at": datetime.now(TZ).isoformat(),
            "updated_at": datetime.now(TZ).isoformat(),
            "metadata": {
                "stars": item.get("stars"),
                "hn_points": None,
                "original_language": analysis.get("language", "en"),
            },
        }
        item["_article"] = article

    return valid


# ---------------------------------------------------------------------------
# Step 4: 保存 (Save)
# ---------------------------------------------------------------------------


def _next_article_index(source: str) -> int:
    """扫描 articles 目录，获取当日已存在的最大序号。

    Args:
        source: 来源标识（github / rss）。

    Returns:
        下一个可用的序号（已有最大序号 + 1）。
    """
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    prefix = f"{today}-{source}-"
    max_idx = 0

    if ARTICLES_DIR.exists():
        for f in ARTICLES_DIR.glob(f"{prefix}*.json"):
            try:
                num = int(f.stem[len(prefix):])
                max_idx = max(max_idx, num)
            except ValueError:
                pass
    return max_idx + 1


def _do_save(
    organized: list[dict[str, Any]],
    raw_data: dict[str, list[dict[str, Any]]],
    dry_run: bool,
) -> dict[str, int]:
    """执行保存步骤：将文章保存为 JSON 文件，原始数据存档。

    Args:
        organized: 整理后的条目列表（含 _article）。
        raw_data: 按 source 分组的原始采集数据。
        dry_run: 是否为干跑模式。

    Returns:
        各 source 保存的文章数量统计。
    """
    saved_count: dict[str, int] = {}

    # --- 保存 raw 数据 ---
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    for source, items in raw_data.items():
        raw_file = RAW_DIR / f"{today}-{source}.json"
        raw_payload = {
            "collected_at": datetime.now(TZ).isoformat(),
            "source": source,
            "count": len(items),
            "items": items,
        }
        if dry_run:
            logger.info("  [DRY-RUN] Would save raw: %s (%d items)", raw_file.name, len(items))
        else:
            raw_file.write_text(
                json.dumps(raw_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            logger.info("  Raw saved: %s (%d items)", raw_file, len(items))

    # --- 保存 articles ---
    for item in organized:
        article = item.get("_article")
        if not article:
            continue

        source = article["id"].split("-")[3]  # 从 ID 提取 source
        if dry_run:
            saved_count[source] = saved_count.get(source, 0) + 1
            continue

        article_path = ARTICLES_DIR / f"{article['id']}.json"
        article_path.write_text(
            json.dumps(article, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        saved_count[source] = saved_count.get(source, 0) + 1

    if dry_run:
        for source, count in saved_count.items():
            logger.info("  [DRY-RUN] Would save %d articles for %s", count, source)

    return saved_count


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


async def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    """执行完整知识库流水线。

    Args:
        args: 解析后的命令行参数。

    Returns:
        流水线执行统计信息。
    """
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = set(sources) - {"github", "rss"}
    if unknown:
        raise ValueError(f"未知采集源: {unknown}，有效值: github, rss")

    print("=" * 60)
    print("  AI 知识库自动化流水线")
    print("=" * 60)
    print(f"  Sources : {', '.join(sources)}")
    print(f"  Limit   : {args.limit}")
    print(f"  Dry run : {args.dry_run}")
    print("=" * 60)
    print()

    # --- Step 1: 采集 ---
    print("[Step 1/4] 采集 (Collect)")
    collected = await _do_collect(sources, args.limit)
    total_collected = sum(len(v) for v in collected.values())
    print(f"  Total collected: {total_collected} items\n")

    # --- Step 2: 分析 ---
    print("[Step 2/4] 分析 (Analyze)")
    if total_collected == 0:
        print("  No items to analyze.\n")
        return {"collected": 0, "analyzed": 0, "saved": 0}

    analyzed = await _do_analyze(collected, args.dry_run)
    failed = sum(1 for it in analyzed if "_error" in it.get("_analysis", {}))
    print(f"  Analyzed: {len(analyzed) - failed}/{len(analyzed)} items"
          + (f" ({failed} failed)" if failed else "") + "\n")

    # --- Step 3: 整理 ---
    print("[Step 3/4] 整理 (Organize)")
    all_organized: list[dict[str, Any]] = []
    for source in sorted(collected.keys()):
        source_items = [it for it in analyzed if it.get("_source") == source]
        start_idx = _next_article_index(source)
        organized = _do_organize(source_items, source, start_idx)
        all_organized.extend(organized)

    if all_organized:
        scores = [it["_article"]["relevance_score"] for it in all_organized]
        print(f"  Organized: {len(all_organized)} articles")
        print(f"  Relevance: avg={sum(scores)/len(scores):.2f}, "
              f"min={min(scores):.2f}, max={max(scores):.2f}")
    else:
        print("  Organized: 0 articles")
    print()

    # --- Step 4: 保存 ---
    print("[Step 4/4] 保存 (Save)")
    saved = _do_save(all_organized, collected, args.dry_run)
    total_saved = sum(saved.values()) if not args.dry_run else 0
    if args.dry_run:
        print(f"  DRY RUN — would save {sum(saved.values())} articles")
    else:
        print(f"  Saved: {total_saved} articles → {ARTICLES_DIR}")
    print()

    # --- 汇总 ---
    print("=" * 60)
    print("  Pipeline completed!")
    status = "DRY RUN — no files written" if args.dry_run else f"{total_saved} articles saved"
    print(f"  {status}")
    print("=" * 60)

    return {
        "collected": total_collected,
        "analyzed": len(analyzed),
        "organized": len(all_organized),
        "saved": sum(saved.values()),
    }


def main(argv: list[str] | None = None) -> None:
    """CLI 入口。

    Args:
        argv: 命令行参数，为 None 时使用 sys.argv。
    """
    args = _parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
