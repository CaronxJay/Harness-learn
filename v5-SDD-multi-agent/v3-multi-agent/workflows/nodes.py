#!/usr/bin/env python3
"""LangGraph 工作流节点函数 — 采集 / 分析 / 整理 / 审核 / 保存。

每个节点是纯函数：接收 KBState，返回 dict（部分状态更新）。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflows.model_client import BudgetExceededError, accumulate_usage, chat, chat_json
from tests.security import filter_output, sanitize_input
from workflows.state import KBState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_HEADERS: dict[str, str] = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "AI-Knowledge-Base/1.0",
}
if gh_token := os.getenv("GITHUB_TOKEN", ""):
    GITHUB_HEADERS["Authorization"] = f"Bearer {gh_token}"

CATEGORIES = (
    "agent-framework / llm / research / application / "
    "infrastructure / benchmark / security / multimodal"
)

ARTICLES_DIR = (
    Path(__file__).resolve().parent.parent / "knowledge" / "articles"
)


# ---------------------------------------------------------------------------
# collect_node
# ---------------------------------------------------------------------------


def collect_node(state: KBState) -> dict[str, Any]:
    """调用 GitHub Search API 采集 AI 相关仓库。

    读取 state["plan"]["per_source_limit"] 控制每源抓取量。
    """
    print("[CollectNode] 开始采集 GitHub AI 相关仓库...")

    plan = state.get("plan", {}) or {}
    per_page = int(plan.get("per_source_limit", 10))

    search_queries = [
        "ai agent framework",
        "large language model tools",
        "multi agent system",
    ]
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    idx = 1

    for query in search_queries:
        encoded = urllib.parse.quote(query)
        url = f"{GITHUB_SEARCH_URL}?q={encoded}&sort=stars&order=desc&per_page={per_page}"

        logger.info("[CollectNode] 搜索: %s", query)
        req = urllib.request.Request(url, headers=GITHUB_HEADERS)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("[CollectNode] GitHub API 错误: %s %s", exc.code, exc.reason)
            continue
        except Exception as exc:
            logger.warning("[CollectNode] 网络错误: %s", exc)
            continue

        for item in data.get("items", []):
            html_url = item["html_url"]
            if html_url in seen_urls:
                continue
            seen_urls.add(html_url)

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sources.append({
                "id": f"{today}-github-{idx:03d}",
                "source": "github_trending",
                "title": item["full_name"],
                "url": html_url,
                "description": (item.get("description") or "")[:300],
                "metadata": {
                    "stars": item["stargazers_count"],
                    "hn_points": None,
                    "language": (item.get("language") or "").lower(),
                },
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
            idx += 1

    print(f"[CollectNode] 采集完成，共 {len(sources)} 条")

    # 对每条 source 的文本字段做注入清洗
    total_warnings = 0
    for s in sources:
        for field in ("title", "description"):
            if field in s and isinstance(s[field], str):
                cleaned, warnings = sanitize_input(s[field])
                s[field] = cleaned
                total_warnings += len(warnings)
                if warnings:
                    logger.warning(
                        "[Security] %s %s 检出注入模式：%s",
                        s.get("url", "?"), field, warnings,
                    )

    if total_warnings > 0:
        print(f"[Security] collect 阶段共拦截 {total_warnings} 处可疑输入")

    return {"sources": sources}


# ---------------------------------------------------------------------------
# analyze_node
# ---------------------------------------------------------------------------

ANALYZE_SYSTEM = (
    "You are an AI/LLM expert analyst. For each GitHub repository, generate a "
    "structured Chinese analysis. Be concise and precise.\n"
    "Return valid JSON only."
)

ANALYZE_PROMPT = (
    "Analyze this GitHub repository in Chinese:\n"
    "Name: {name}\n"
    "Description: {description}\n"
    "Stars: {stars}\n"
    "Language: {language}\n\n"
    "Return JSON:\n"
    '{{"title": "中文提炼标题", "summary": "中文摘要（≤200字）", '
    '"summary_en": "英文摘要（≤200字）", '
    '"tags": ["tag1", "tag2", ...], '
    f'"category": "{CATEGORIES}", '
    '"relevance_score": 0.92}}\n'
    "relevance_score: 0.0-1.0, how relevant to AI/LLM/Agent field."
)

# relevance_threshold 由 planner 策略决定，organize_node 从 state["plan"] 读取


async def analyze_node(state: KBState) -> dict[str, Any]:
    """对每条 source 调用 LLM 生成中文摘要、标签、评分。

    跳过 sources 为空的场景。
    """
    print("[AnalyzeNode] 开始 LLM 分析...")

    sources = state.get("sources", [])
    if not sources:
        print("[AnalyzeNode] 无待分析数据，跳过")
        return {"analyses": []}

    tracker = deepcopy(state.get("cost_tracker", {}))
    analyses: list[dict[str, Any]] = []

    for item in sources:
        prompt = ANALYZE_PROMPT.format(
            name=item["title"],
            description=item.get("description", ""),
            stars=item.get("metadata", {}).get("stars", 0),
            language=item.get("metadata", {}).get("language", ""),
        )

        try:
            result, usage = await chat_json(prompt, system=ANALYZE_SYSTEM, temperature=0.8, node_name="analyze")
            accumulate_usage(tracker, usage)
        except BudgetExceededError:
            raise
        except Exception as exc:
            logger.warning("[AnalyzeNode] 分析失败 %s: %s", item["id"], exc)
            continue

        analyses.append({
            "source_id": item["id"],
            "title": result.get("title", item["title"]),
            "summary": result.get("summary", "")[:200],
            "summary_en": result.get("summary_en", "")[:200],
            "tags": result.get("tags", []),
            "category": result.get("category", ""),
            "relevance_score": float(result.get("relevance_score", 0)),
            "analysis_cost_tokens": usage.total_tokens,
        })

    print(f"[AnalyzeNode] 分析完成，成功 {len(analyses)}/{len(sources)} 条")
    return {"analyses": analyses, "cost_tracker": tracker}


# ---------------------------------------------------------------------------
# organize_node
# ---------------------------------------------------------------------------

ORGANIZE_CORRECT_SYSTEM = (
    "You are an editor who fixes analysis articles based on review feedback. "
    "Return valid JSON only."
)

ORGANIZE_CORRECT_PROMPT = (
    "Review feedback about this article:\n{feedback}\n\n"
    "Original article (JSON):\n{article}\n\n"
    "Revise the article to address the feedback. Return corrected JSON "
    "with the same fields: title, summary, summary_en, tags, category, "
    "relevance_score."
)


async def organize_node(state: KBState) -> dict[str, Any]:
    """过滤低分、URL 去重，如有审核反馈则调 LLM 定向修正。

    将 analyses 转为 articles 格式，填入 KBState.articles。
    """
    print("[OrganizeNode] 开始整理...")

    analyses = state.get("analyses", [])
    if not analyses:
        print("[OrganizeNode] 无待整理数据，跳过")
        return {"articles": []}

    iteration = state.get("iteration", 0)
    feedback = state.get("review_feedback", "")
    tracker = deepcopy(state.get("cost_tracker", {}))

    # 相关度阈值：从 plan 读取，默认 0.5
    plan = state.get("plan", {}) or {}
    relevance_threshold = float(plan.get("relevance_threshold", 0.5))

    # 过滤低分
    filtered = [a for a in analyses if a.get("relevance_score", 0) >= relevance_threshold]
    print(f"[OrganizeNode] 过滤低分(<{relevance_threshold}): {len(analyses)} → {len(filtered)} 条")

    # URL 去重
    seen_urls: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for a in filtered:
        # URL 来源于 source，通过 source_id 反查
        url_key = a.get("source_id", "")
        if url_key not in seen_urls:
            seen_urls.add(url_key)
            deduped.append(a)
    print(f"[OrganizeNode] URL 去重: {len(filtered)} → {len(deduped)} 条")

    # 如有审核反馈，调用 LLM 逐条修正
    if iteration > 0 and feedback:
        print(f"[OrganizeNode] 检测到审核反馈 (iteration={iteration})，开始 LLM 修正...")
        corrected: list[dict[str, Any]] = []
        for article in deduped:
            prompt = ORGANIZE_CORRECT_PROMPT.format(
                feedback=feedback,
                article=json.dumps(article, ensure_ascii=False, indent=2),
            )
            try:
                result, usage = await chat_json(
                    prompt, system=ORGANIZE_CORRECT_SYSTEM, temperature=0.5
                )
                accumulate_usage(tracker, usage)
                # 保留 source_id
                result.setdefault("source_id", article.get("source_id"))
                corrected.append(result)
            except BudgetExceededError:
                raise
            except Exception as exc:
                logger.warning("[OrganizeNode] 修正失败: %s，保留原文", exc)
                corrected.append(article)
        deduped = corrected

    # 构建 articles（含完整元数据）
    now_iso = datetime.now(timezone.utc).isoformat()
    articles: list[dict[str, Any]] = []
    for i, a in enumerate(deduped):
        source_id = a.get("source_id", "")
        articles.append({
            "id": source_id,
            "title": a.get("title", ""),
            "source": "github_trending",
            "source_url": "",
            "language": "en",
            "summary": a.get("summary", "")[:200],
            "summary_en": a.get("summary_en", ""),
            "tags": a.get("tags", []),
            "category": a.get("category", ""),
            "relevance_score": a.get("relevance_score", 0),
            "status": "draft",
            "created_at": now_iso,
            "updated_at": now_iso,
            "metadata": {"stars": None, "hn_points": None, "original_language": "en"},
        })

    # 写盘前对每条 article 的文本字段做 PII 掩码
    total_pii = 0
    for art in articles:
        for field in ("title", "summary", "summary_en"):
            if field in art and isinstance(art[field], str):
                filtered, detections = filter_output(art[field], mask=True)
                art[field] = filtered
                total_pii += len(detections)
                if detections:
                    logger.warning(
                        "[Security] %s %s 掩码 PII：%s",
                        art.get("id", "?"), field, detections,
                    )

    if total_pii > 0:
        print(f"[Security] organize 阶段共掩码 {total_pii} 处 PII")

    print(f"[OrganizeNode] 整理完成，产出 {len(articles)} 条文章")

    result: dict[str, Any] = {"articles": articles, "cost_tracker": tracker}
    # 如有 LLM 修正，同步更新 analyses，确保 reviewer 重入时看到修正后数据
    if iteration > 0 and feedback:
        result["analyses"] = deduped
    return result


# ---------------------------------------------------------------------------
# review_node
# ---------------------------------------------------------------------------

REVIEW_SYSTEM = (
    "You are a strict quality auditor for AI knowledge base articles. "
    "Evaluate the batch of articles on four dimensions. Return valid JSON only."
)

REVIEW_PROMPT = (
    "Evaluate the following AI knowledge base articles on four dimensions "
    "(each 1-10):\n"
    "  summary_quality: 中文摘要是否准确、简洁、抓住核心\n"
    "  tag_accuracy: 标签是否贴合内容、无杜撰\n"
    "  category_reasonableness: 分类是否符合给定 9 类枚举\n"
    "  consistency: 标题/摘要/分类之间是否自洽\n\n"
    "Articles:\n{articles}\n\n"
    'Return JSON:\n'
    '{{"passed": true/false, "overall_score": 7.5, "feedback": "...", '
    '"scores": {{"summary_quality": 8, "tag_accuracy": 7, '
    '"category_reasonableness": 8, "consistency": 7}}}}'
)

PASS_THRESHOLD = 7.0  # overall_score >= 7.0 视为通过


async def review_node(state: KBState) -> dict[str, Any]:
    """LLM 四维度审核 articles 质量。

    - iteration >= 2 时强制通过（不再调用 LLM）
    - 否则调用 LLM 评分，overall_score >= 7.0 通过
    """
    print("[ReviewNode] 开始审核...")

    iteration = state.get("iteration", 0)

    # iteration >= 2 → 强制通过
    if iteration >= 2:
        print(f"[ReviewNode] iteration={iteration} >= 2，强制通过")
        return {
            "review_feedback": "",
            "review_passed": True,
            "iteration": iteration,
        }

    articles = state.get("articles", [])
    if not articles:
        print("[ReviewNode] 无文章待审核，视为通过")
        return {"review_feedback": "", "review_passed": True, "iteration": iteration}

    tracker = deepcopy(state.get("cost_tracker", {}))
    articles_json = json.dumps(articles, ensure_ascii=False, indent=2)

    try:
        result, usage = await chat_json(
            REVIEW_PROMPT.format(articles=articles_json),
            system=REVIEW_SYSTEM,
            temperature=0.2,
        )
        accumulate_usage(tracker, usage)
    except BudgetExceededError:
        raise
    except Exception as exc:
        logger.warning("[ReviewNode] LLM 审核失败: %s，强制通过", exc)
        return {
            "review_feedback": f"LLM 审核异常: {exc}",
            "review_passed": True,
            "iteration": iteration,
            "cost_tracker": tracker,
        }

    passed = bool(result.get("passed", False))
    overall_score = float(result.get("overall_score", 0))
    feedback = str(result.get("feedback", ""))
    scores = result.get("scores", {})

    # 如果 passed=False 但 overall_score >= PASS_THRESHOLD，覆盖通过
    if not passed and overall_score >= PASS_THRESHOLD:
        passed = True

    print(
        f"[ReviewNode] 审核完成: passed={passed} score={overall_score:.1f} "
        f"(summary={scores.get('summary_quality')} "
        f"tag={scores.get('tag_accuracy')} "
        f"cat={scores.get('category_reasonableness')} "
        f"consistency={scores.get('consistency')})"
    )

    next_iteration = iteration
    if not passed:
        next_iteration = iteration + 1

    return {
        "review_feedback": feedback,
        "review_passed": passed,
        "iteration": next_iteration,
        "cost_tracker": tracker,
    }


# ---------------------------------------------------------------------------
# save_node
# ---------------------------------------------------------------------------


def save_node(state: KBState) -> dict[str, Any]:
    """将 articles 写入 knowledge/articles/ 目录的 JSON 文件，并更新 index.json。

    每条文章写入独立文件，文件名使用 article.id。
    """
    print("[SaveNode] 开始保存...")

    articles = state.get("articles", [])
    if not articles:
        print("[SaveNode] 无文章待保存，跳过")
        return {}

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    saved = 0
    for article in articles:
        article_id = article.get("id", "")
        if not article_id:
            logger.warning("[SaveNode] 跳过无 ID 的文章: %s", article.get("title"))
            continue

        filepath = ARTICLES_DIR / f"{article_id}.json"
        article["updated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            filepath.write_text(
                json.dumps(article, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            saved += 1
        except IOError as exc:
            logger.error("[SaveNode] 写入失败 %s: %s", filepath, exc)

    # 更新 index.json
    index_path = ARTICLES_DIR / "index.json"
    try:
        existing: list[dict[str, Any]] = []
        if index_path.exists():
            existing = json.loads(index_path.read_text(encoding="utf-8"))
        # 合并：新文章替换同 ID 旧条目
        existing_ids = {a.get("id") for a in existing}
        for article in articles:
            if article.get("id") in existing_ids:
                for i, old in enumerate(existing):
                    if old.get("id") == article.get("id"):
                        existing[i] = article
                        break
            else:
                existing.append(article)
        index_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except (IOError, json.JSONDecodeError) as exc:
        logger.error("[SaveNode] index.json 更新失败: %s", exc)

    print(f"[SaveNode] 保存完成: {saved}/{len(articles)} 条文章")
    return {}
