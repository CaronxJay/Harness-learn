#!/usr/bin/env python3
"""Router 路由模式 — 两层意图分类 + 分发处理。

Layer 1: Keyword-based quick match (zero cost, no LLM)
Layer 2: LLM classification fallback (for ambiguous queries)

Three intents:
  - github_search: Search GitHub repos via API
  - knowledge_query: Search local knowledge base
  - general_chat: Direct LLM chat
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from pipeline.model_client import Usage, chat_with_retry, create_provider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer 1: Keyword Quick Match
# ---------------------------------------------------------------------------

KEYWORD_RULES: list[tuple[str, list[str]]] = [
    (
        "github_search",
        [
            "github", "repo", "repository", "开源项目", "开源", "代码", "源码",
            "星标", "star", "fork", "仓库", "open source", "github 上",
        ],
    ),
    (
        "knowledge_query",
        [
            "知识库", "文章", "论文", "paper", "arxiv", "transformer",
            "agent", "llm", "大模型", "科研", "研究", "research",
            "trending", "hacker news", "hn", "科技", "summary",
            "多模态", "mcp", "rag", "gpt", "deepseek",
        ],
    ),
]

# O(1) keyword lookup for handlers that need to reference rules by intent
_KEYWORD_DICT: dict[str, list[str]] = dict(KEYWORD_RULES)


def _classify_keywords(query: str) -> str | None:
    """Try to classify intent by ordered keyword matching.

    Rules are evaluated in priority order — the first intent whose keywords
    match the query wins.  Returns None if no rule matches.

    Args:
        query: The user query string.

    Returns:
        Intent name, or None if no keyword matched.
    """
    query_lower = query.lower()
    for intent, keywords in KEYWORD_RULES:
        if any(kw in query_lower for kw in keywords):
            return intent
    return None


# ---------------------------------------------------------------------------
# chat() / chat_json() wrappers
# ---------------------------------------------------------------------------


async def chat(
    prompt: str,
    provider: str | None = None,
    system: str | None = None,
) -> tuple[str, Usage]:
    """Call LLM and return (text, usage) tuple.

    Args:
        prompt: User message content.
        provider: Provider name (deepseek / qwen / openai).
        system: Optional system prompt.

    Returns:
        Tuple of (response_text, usage_stats).
    """
    llm = create_provider(provider)

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await chat_with_retry(llm, messages)
        return response.content, response.usage
    finally:
        await llm.close()


def _extract_json(text: str) -> str:
    """Robustly extract JSON substring from LLM response.

    Handles markdown code fences and accidental surrounding text.

    Args:
        text: Raw LLM response.

    Returns:
        Clean JSON string.
    """
    text = text.strip()
    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if len(lines) > 1 else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Fallback: find first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


async def chat_json(
    prompt: str,
    provider: str | None = None,
    system: str | None = None,
) -> dict[str, Any]:
    """Call LLM and return parsed JSON response.

    Args:
        prompt: User message content.
        provider: Provider name.
        system: Optional system prompt.

    Returns:
        Parsed JSON dict.
    """
    json_system = (
        (system or "")
        + "\nRespond with valid JSON only. No other text, no markdown fences."
    )
    text, _ = await chat(prompt, provider, json_system)
    clean = _extract_json(text)
    return json.loads(clean)


# ---------------------------------------------------------------------------
# Intent Handlers
# ---------------------------------------------------------------------------

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

GITHUB_HEADERS: dict[str, str] = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "AI-Knowledge-Base/1.0",
}
if gh_token := os.getenv("GITHUB_TOKEN", ""):
    GITHUB_HEADERS["Authorization"] = f"Bearer {gh_token}"


def _handle_github_search(query: str) -> str:
    """Search GitHub repositories via GitHub Search API.

    Args:
        query: The user query string.

    Returns:
        Formatted search results.
    """
    search_terms = query
    for kw in _KEYWORD_DICT["github_search"]:
        search_terms = re.sub(re.escape(kw), "", search_terms, flags=re.IGNORECASE)
    search_terms = " ".join(search_terms.split())  # normalize whitespace

    if not search_terms:
        search_terms = "ai agent"

    encoded = urllib.parse.quote(search_terms)
    url = f"{GITHUB_SEARCH_URL}?q={encoded}&sort=stars&order=desc&per_page=5"

    logger.info("GitHub Search: %s", url)

    req = urllib.request.Request(url, headers=GITHUB_HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        logger.error("GitHub API error: %s %s", exc.code, exc.reason)
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("message", exc.reason)
        except (json.JSONDecodeError, ValueError):
            detail = exc.reason
        return f"GitHub 搜索失败: HTTP {exc.code} — {detail}"
    except Exception as exc:
        logger.error("GitHub search error: %s", exc)
        return f"GitHub 搜索失败: {exc}"

    items = data.get("items", [])
    if not items:
        return f"未找到与「{search_terms}」相关的 GitHub 仓库。"

    lines = [f"GitHub 搜索结果（关键词: {search_terms}）\n"]
    for i, repo in enumerate(items, 1):
        lines.append(
            f"{i}. **{repo['full_name']}**  ⭐{repo['stargazers_count']}\n"
            f"   {repo.get('description', '无描述') or '无描述'}\n"
            f"   {repo['html_url']}\n"
        )

    return "\n".join(lines)


def _handle_knowledge_query(query: str) -> str:
    """Search local knowledge base for relevant articles.

    Uses knowledge/articles/index.json if available; otherwise scans
    all .json files in the articles directory.

    Args:
        query: The user query string.

    Returns:
        Formatted search results.
    """
    articles_dir = Path(__file__).resolve().parent.parent / "knowledge" / "articles"

    if not articles_dir.exists():
        return "知识库目录不存在。请先运行采集流程。"

    # Prefer index.json, build in-memory if absent
    index_path = articles_dir / "index.json"
    if index_path.exists():
        try:
            articles = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("Failed to read index.json: %s", exc)
            articles = []
    else:
        articles = []
        for fpath in sorted(articles_dir.glob("*.json")):
            if fpath.name == "index.json":
                continue
            try:
                article = json.loads(fpath.read_text(encoding="utf-8"))
                articles.append(article)
            except (json.JSONDecodeError, IOError) as exc:
                logger.warning("Failed to read %s: %s", fpath, exc)

    query_lower = query.lower()
    results: list[dict[str, Any]] = []

    for article in articles:
        title = (article.get("title") or "").lower()
        summary = (article.get("summary") or "").lower()
        tags = " ".join(article.get("tags") or []).lower()

        score = 0
        for term in query_lower.split():
            if len(term) < 2:
                continue
            if term in title:
                score += 3
            if term in summary:
                score += 2
            if term in tags:
                score += 1

        if score > 0:
            results.append({**article, "_score": score})

    results.sort(key=lambda r: r["_score"], reverse=True)
    results = results[:5]

    if not results:
        return f"知识库中未找到与「{query}」相关的文章。"

    lines = [f"知识库检索结果（共 {len(results)} 条）\n"]
    for i, article in enumerate(results, 1):
        lines.append(
            f"{i}. **{article.get('title', '无标题')}**  (相关度: {article['_score']})\n"
            f"   来源: {article.get('source', '未知')}  |  "
            f"标签: {', '.join(article.get('tags', [])[:4])}\n"
            f"   {article.get('summary', '无摘要')[:120]}...\n"
        )

    return "\n".join(lines)


async def _handle_general_chat(query: str) -> str:
    """Handle general chat via LLM.

    Args:
        query: The user query string.

    Returns:
        LLM response text, or a polite fallback message if LLM is unavailable.
    """
    system = "You are a helpful AI assistant. Answer concisely."
    try:
        text, _ = await chat(query, system=system)
        return text
    except Exception as exc:
        logger.warning("LLM chat failed: %s", exc)
        return (
            f"抱歉，当前 LLM 服务不可用 ({exc})。\n"
            f"您可以尝试更具体地描述您的需求，例如：\n"
            f"  - 「搜索 GitHub 上的 xxx 项目」来查找开源项目\n"
            f"  - 「知识库里有什么关于 xxx 的内容」来检索已采集的技术文章"
        )


# ---------------------------------------------------------------------------
# Layer 2: LLM Classification Fallback
# ---------------------------------------------------------------------------

CLASSIFY_PROMPT = (
    "Classify the user query into exactly one of these intents:\n"
    "- github_search: Searching for GitHub repos, open-source projects, "
    "code, or repository info\n"
    "- knowledge_query: Searching the AI/LLM knowledge base for articles, "
    "papers, tech news, or research\n"
    "- general_chat: General conversation, Q&A, or anything else\n\n"
    'User query: "{query}"\n\n'
    'Respond with JSON: {{"intent": "<intent_name>"}}'
)


async def _classify_by_llm(query: str) -> str:
    """Use LLM to classify the query intent (fallback for ambiguous queries).

    Args:
        query: The user query string.

    Returns:
        One of: github_search / knowledge_query / general_chat
    """
    prompt = CLASSIFY_PROMPT.format(query=query)

    try:
        result = await chat_json(prompt)
        intent = result.get("intent", "general_chat")
    except Exception as exc:
        logger.warning("LLM classification failed: %s, defaulting to general_chat", exc)
        intent = "general_chat"

    valid = {"github_search", "knowledge_query", "general_chat"}
    if intent not in valid:
        intent = "general_chat"

    return intent


# ---------------------------------------------------------------------------
# Unified Entry Point
# ---------------------------------------------------------------------------


async def route(query: str) -> str:
    """Route a user query to the appropriate handler.

    Two-layer classification:
      1. Keyword matching (fast, free)
      2. LLM classification (fallback for ambiguous / no-match queries)

    Args:
        query: The user query string.

    Returns:
        Response string from the matched handler.
    """
    if not query or not query.strip():
        return "请输入查询内容。"

    query = query.strip()
    logger.info("Routing: %s", query[:100])

    # Layer 1: Keyword fast match
    intent = _classify_keywords(query)

    # Layer 2: LLM fallback
    if intent is None:
        logger.info("Keyword match ambiguous, falling back to LLM classifier")
        intent = await _classify_by_llm(query)

    logger.info("Intent: %s ← %s", intent, query[:80])

    # Dispatch
    if intent == "github_search":
        return _handle_github_search(query)
    elif intent == "knowledge_query":
        return _handle_knowledge_query(query)
    else:
        return await _handle_general_chat(query)


# ---------------------------------------------------------------------------
# Test Entry
# ---------------------------------------------------------------------------


def _run_tests() -> None:
    """Run router self-tests."""
    print("=" * 60)
    print("  patterns/router.py — Router 路由模式测试")
    print("=" * 60)

    # Test 1: Keyword classification
    print("\n[1] 关键词分类测试")
    test_cases = [
        ("帮我搜索 GitHub 上的 agent 框架", "github_search"),
        ("知识库里有没有关于 LLM 的文章", "knowledge_query"),
        ("最近有什么 AI 论文", "knowledge_query"),
        ("今天天气怎么样", None),
        ("github 上有什么新的大模型项目", "github_search"),
        ("帮我找个开源项目", "github_search"),
        ("什么是 transformer 架构", "knowledge_query"),
    ]
    for query, expected in test_cases:
        result = _classify_keywords(query)
        status = "✓" if result == expected else "✗"
        print(f"    {status} 「{query}」→ {result} (expected: {expected})")

    # Test 2: Handler connectivity
    print("\n[2] 处理器连通性测试")

    print(f"    GitHub Search URL 编码: {urllib.parse.quote('AI agent framework')}")

    articles_dir = Path(__file__).resolve().parent.parent / "knowledge" / "articles"
    if articles_dir.exists():
        count = len(list(articles_dir.glob("*.json")))
        print(f"    知识库文章数: {count}")
    else:
        print("    知识库目录不存在")

    # Test 3: Live routing test (requires API key)
    api_key = os.getenv("API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        print(f"    LLM 已配置 (provider: {os.getenv('LLM_PROVIDER', 'deepseek')})")
        print("\n    运行实时路由测试...")

        async def _live_test() -> None:
            test_queries = [
                "什么是 AI Agent",
            ]
            for q in test_queries:
                print(f"\n    ── 查询: {q}")
                try:
                    result = await route(q)
                    if len(result) > 300:
                        result = result[:300] + "..."
                    print(f"    结果: {result}")
                except Exception as exc:
                    print(f"    失败: {exc}")

        asyncio.run(_live_test())
    else:
        print("    未检测到 API_KEY，跳过实时路由测试。")

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = asyncio.run(route(query))
        print(result)
    else:
        _run_tests()
