#!/usr/bin/env python3
"""MCP Server — AI 知识库检索服务。

提供 JSON-RPC 2.0 over stdio 接口，让 AI 工具可以搜索
knowledge/articles/ 目录中的结构化文章。
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class MCPError(Exception):
    """带 JSON-RPC 错误码的 MCP 异常。"""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# 知识库
# ---------------------------------------------------------------------------


class KnowledgeBase:
    """本地知识库索引。"""

    def __init__(self, articles_dir: Path) -> None:
        self._articles_dir = articles_dir
        self._articles: dict[str, dict[str, Any]] = {}
        self._load()

    # ---- 加载 ----

    def _load(self) -> None:
        """扫描 articles 目录，加载所有 JSON 文件。"""
        if not self._articles_dir.exists():
            logger.warning("Articles directory not found: %s", self._articles_dir)
            return

        files = sorted(self._articles_dir.glob("*.json"))
        for fp in files:
            try:
                article = json.loads(fp.read_text(encoding="utf-8"))
                article_id = article.get("id") or fp.stem
                self._articles[article_id] = article
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load %s: %s", fp.name, exc)

        logger.info("Loaded %d articles from %s", len(self._articles), self._articles_dir)

    def reload(self) -> None:
        """重新加载索引。"""
        self._articles.clear()
        self._load()

    @property
    def count(self) -> int:
        return len(self._articles)

    # ---- 工具方法 ----

    def search(self, keyword: str, limit: int = 5) -> list[dict[str, Any]]:
        """关键词搜索文章。

        Args:
            keyword: 搜索关键词（空格分隔支持多词）。
            limit: 最大返回条数。

        Returns:
            匹配文章列表，按相关度降序，含 _match_score。
        """
        keywords = keyword.lower().split()
        if not keywords:
            return []

        scored: list[tuple[dict[str, Any], float]] = []

        for article in self._articles.values():
            title = (article.get("title") or "").lower()
            summary = (article.get("summary") or "").lower()
            tags_text = " ".join(article.get("tags") or []).lower()
            source = (article.get("source") or "").lower()

            combined = f"{title} {summary} {tags_text} {source}"
            score = 0.0
            for kw in keywords:
                if kw in title:
                    score += 3.0
                if kw in summary:
                    score += 1.5
                if kw in tags_text:
                    score += 2.0
                if kw in source:
                    score += 0.5

            if score > 0:
                scored.append((article, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            {
                "id": art.get("id", ""),
                "title": art.get("title", ""),
                "source": art.get("source", ""),
                "source_url": art.get("source_url", ""),
                "summary": (art.get("summary") or "")[:200],
                "relevance_score": art.get("relevance_score") or art.get("score", 0),
                "tags": art.get("tags", []),
                "category": art.get("category", ""),
                "_match_score": round(score, 2),
            }
            for art, score in scored[:limit]
        ]

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """按 ID 获取完整文章。

        Args:
            article_id: 文章唯一标识。

        Returns:
            文章完整 JSON，不存在则返回 None。
        """
        return self._articles.get(article_id)

    def stats(self) -> dict[str, Any]:
        """知识库统计信息。

        Returns:
            包含总数、来源分布、分类、热门标签的字典。
        """
        articles = list(self._articles.values())
        if not articles:
            return {
                "total_articles": 0,
                "sources": {},
                "categories": {},
                "top_tags": {},
                "avg_relevance_score": 0,
            }

        sources = Counter(a.get("source", "unknown") for a in articles)
        categories = Counter(a.get("category") for a in articles if a.get("category"))
        all_tags: Counter[str] = Counter()
        for a in articles:
            for tag in a.get("tags") or []:
                all_tags[tag] += 1

        scores = [
            a.get("relevance_score") or a.get("score", 0)
            for a in articles
        ]

        return {
            "total_articles": len(articles),
            "sources": dict(sources.most_common()),
            "categories": dict(categories.most_common()),
            "top_tags": dict(all_tags.most_common(15)),
            "avg_relevance_score": round(
                sum(scores) / len(scores), 3
            ),
        }


# ---------------------------------------------------------------------------
# JSON-RPC Server
# ---------------------------------------------------------------------------


class MCPServer:
    """MCP JSON-RPC 2.0 over stdio 服务器。"""

    SERVER_NAME = "knowledge-base"
    SERVER_VERSION = "1.0.0"
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, kb: KnowledgeBase) -> None:
        self._kb = kb

    def run(self) -> None:
        """主循环：逐行读取 stdin JSON-RPC，写入 stdout 响应。"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Invalid JSON input: %s", exc)
                continue

            response = self._dispatch(request)
            if response is not None:
                sys.stdout.write(
                    json.dumps(response, ensure_ascii=False) + "\n"
                )
                sys.stdout.flush()

    # ---- 分发 ----

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """路由 JSON-RPC 请求到对应处理方法。"""
        method = request.get("method", "")
        request_id = request.get("id")

        if request_id is None:
            logger.debug("Notification: %s", method)
            return None

        handler: dict[str, Any] = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
        }

        if method not in handler:
            return self._error(request_id, -32601, f"Method not found: {method}")

        try:
            result = handler[method](request.get("params", {}), request_id)
        except MCPError as exc:
            return self._error(request_id, exc.code, exc.message)
        except Exception as exc:
            logger.exception("Unexpected error in %s", method)
            return self._error(request_id, -32603, str(exc))

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }

    # ---- MCP 生命周期 ----

    def _handle_initialize(
        self, params: dict[str, Any], request_id: Any
    ) -> dict[str, Any]:
        """initialize — 握手，返回服务器能力声明。"""
        client_info = params.get("clientInfo", {})
        logger.info(
            "Initialize from %s v%s (protocol %s)",
            client_info.get("name", "unknown"),
            client_info.get("version", ""),
            params.get("protocolVersion", ""),
        )
        return {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": self.SERVER_NAME,
                "version": self.SERVER_VERSION,
            },
        }

    # ---- tools/list ----

    def _handle_tools_list(
        self, params: dict[str, Any], request_id: Any
    ) -> dict[str, Any]:
        """tools/list — 返回可用工具清单。"""
        return {
            "tools": [
                {
                    "name": "search_articles",
                    "description": (
                        "Search the AI knowledge base by keyword. "
                        "Matches against article title, summary, and tags. "
                        "Returns ranked results with relevance scores."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": (
                                    "Search keyword. "
                                    "Supports multiple words separated by spaces."
                                ),
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results to return (default: 5).",
                                "default": 5,
                            },
                        },
                        "required": ["keyword"],
                    },
                },
                {
                    "name": "get_article",
                    "description": "Get the full content of an article by its ID.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "article_id": {
                                "type": "string",
                                "description": (
                                    "Article unique ID, "
                                    "e.g. '2026-05-06-github-001'."
                                ),
                            },
                        },
                        "required": ["article_id"],
                    },
                },
                {
                    "name": "knowledge_stats",
                    "description": (
                        "Get knowledge base statistics: "
                        "total articles, source distribution, "
                        "categories, and top tags."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    },
                },
            ],
        }

    # ---- tools/call ----

    def _handle_tools_call(
        self, params: dict[str, Any], request_id: Any
    ) -> dict[str, Any]:
        """tools/call — 执行指定工具并返回结果。"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        if name == "search_articles":
            data = self._kb.search(
                keyword=arguments.get("keyword", ""),
                limit=int(arguments.get("limit", 5)),
            )
        elif name == "get_article":
            article = self._kb.get_article(arguments.get("article_id", ""))
            if article is None:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Article not found: {arguments.get('article_id')}",
                        }
                    ],
                    "isError": True,
                }
            data = article
        elif name == "knowledge_stats":
            data = self._kb.stats()
        else:
            raise MCPError(-32601, f"Tool not found: {name}")

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(data, ensure_ascii=False),
                }
            ],
        }

    # ---- 错误响应 ----

    @staticmethod
    def _error(
        request_id: Any, code: int, message: str
    ) -> dict[str, Any]:
        """构造 JSON-RPC 2.0 错误响应。"""
        response: dict[str, Any] = {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
        }
        if request_id is not None:
            response["id"] = request_id
        return response


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    """启动 MCP Server。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    kb = KnowledgeBase(ARTICLES_DIR)
    server = MCPServer(kb)

    logger.info(
        "MCP Knowledge Base Server started (%d articles)", kb.count
    )

    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("MCP Server stopped.")


if __name__ == "__main__":
    main()
