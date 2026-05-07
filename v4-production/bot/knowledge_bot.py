#!/usr/bin/env python3
"""知识库交互模块。

提供基于规则匹配的意图识别、知识搜索、用户订阅管理、三级权限
控制等功能。KnowledgeBot 为统一入口，整合各子模块并暴露简洁的
handle_message 接口。
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 枚举定义
# ---------------------------------------------------------------------------


class Intent(Enum):
    """用户意图枚举。"""

    SEARCH = auto()
    TODAY = auto()
    TOP = auto()
    SUBSCRIBE = auto()
    UNSUBSCRIBE = auto()
    MYSUBS = auto()
    HELP = auto()
    UNKNOWN = auto()


class Permission(Enum):
    """三级权限。"""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """单条搜索结果。"""

    id: str
    title: str
    summary: str
    tags: list[str]
    category: str
    relevance_score: float
    source: str
    source_url: str
    date: str


# ---------------------------------------------------------------------------
# 意图识别（纯函数，无副作用）
# ---------------------------------------------------------------------------

# 斜杠命令 → Intent 直接映射
_COMMAND_PATTERNS: list[tuple[re.Pattern, Intent]] = [
    (re.compile(r"^/(search|s|搜索)\b", re.IGNORECASE), Intent.SEARCH),
    (re.compile(r"^/(today|t|日报|今日)\b", re.IGNORECASE), Intent.TODAY),
    (re.compile(r"^/(top|热榜|热门)\b", re.IGNORECASE), Intent.TOP),
    (re.compile(r"^/(subscribe|sub|订阅)\b", re.IGNORECASE), Intent.SUBSCRIBE),
    (re.compile(r"^/(unsubscribe|unsub|取消订阅|退订)\b", re.IGNORECASE), Intent.UNSUBSCRIBE),
    (re.compile(r"^/(mysubs|my|我的订阅)\b", re.IGNORECASE), Intent.MYSUBS),
    (re.compile(r"^/(help|h|帮助)\b", re.IGNORECASE), Intent.HELP),
]

# 自然语言关键词 → Intent
_NL_PATTERNS: list[tuple[re.Pattern, Intent]] = [
    (re.compile(r"帮助|怎么用|功能|用法|说明|help", re.IGNORECASE), Intent.HELP),
    (re.compile(r"取消订阅|退订|取消关注", re.IGNORECASE), Intent.UNSUBSCRIBE),
    (re.compile(r"我的订阅|订阅列表", re.IGNORECASE), Intent.MYSUBS),
    (re.compile(r"今天|今日|日报|简报|最新", re.IGNORECASE), Intent.TODAY),
    (re.compile(r"热门|热榜|排行|top", re.IGNORECASE), Intent.TOP),
    (re.compile(r"订阅|关注|追踪", re.IGNORECASE), Intent.SUBSCRIBE),
    (re.compile(r"搜索|查询|查找|找.*文章|搜", re.IGNORECASE), Intent.SEARCH),
]


def recognize_intent(text: str) -> tuple[Intent, str]:
    """基于规则匹配识别用户意图。

    优先匹配斜杠命令（/search、/today 等），再回退到自然语言
    关键词匹配。参数部分为去掉匹配前缀后的剩余文本。

    Args:
        text: 用户输入的原始文本。

    Returns:
        (Intent, str) 意图枚举值及参数字符串。
    """
    clean = text.strip()
    if not clean:
        return Intent.UNKNOWN, ""

    # 1) 优先匹配命令前缀
    for pattern, intent in _COMMAND_PATTERNS:
        m = pattern.search(clean)
        if m:
            args = clean[m.end():].strip()
            return intent, args

    # 2) 自然语言关键词匹配
    for pattern, intent in _NL_PATTERNS:
        m = pattern.search(clean)
        if m:
            args = clean[m.end():].strip()
            return intent, args

    return Intent.UNKNOWN, clean


# ---------------------------------------------------------------------------
# 权限管理器
# ---------------------------------------------------------------------------


class PermissionManager:
    """三级权限控制管理器。

    权限持久化到 JSON 文件，默认为空（无人拥有任何权限）。
    支持 grant / revoke / has_permission 操作。

    Attributes:
        _storage: 权限存储文件路径。
        _permissions: user_id → set[Permission] 映射。
    """

    _DEFAULT_PERMISSIONS: dict[Permission, set[str]] = {
        Permission.READ: set(),
        Permission.WRITE: set(),
        Permission.DELETE: set(),
    }

    def __init__(self, storage_path: str = "knowledge/permissions.json") -> None:
        """初始化权限管理器。

        Args:
            storage_path: 权限 JSON 文件路径。
        """
        self._storage = Path(storage_path)
        self._permissions: dict[str, set[Permission]] = defaultdict(set)
        self._load()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def has_permission(self, user_id: str, perm: Permission) -> bool:
        """检查用户是否拥有指定权限。

        Args:
            user_id: 用户标识。
            perm: 权限枚举值。

        Returns:
            True 表示已授权。
        """
        return perm in self._permissions.get(user_id, set())

    def grant(self, user_id: str, perm: Permission) -> None:
        """授予用户指定权限。

        Args:
            user_id: 用户标识。
            perm: 权限枚举值。
        """
        self._permissions[user_id].add(perm)
        self._save()

    def revoke(self, user_id: str, perm: Permission) -> None:
        """撤销用户指定权限。

        Args:
            user_id: 用户标识。
            perm: 权限枚举值。
        """
        self._permissions[user_id].discard(perm)
        self._save()

    def grant_default_read(self, user_id: str) -> None:
        """为新用户授予默认 READ 权限（便捷方法）。"""
        if not self._permissions.get(user_id):
            self.grant(user_id, Permission.READ)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """从 JSON 文件加载权限数据。"""
        if not self._storage.exists():
            return
        try:
            raw = json.loads(self._storage.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("权限文件 %s 读取失败: %s", self._storage, exc)
            return
        for uid, perms in raw.items():
            if isinstance(perms, list):
                for p in perms:
                    try:
                        self._permissions[uid].add(Permission(p))
                    except ValueError:
                        logger.warning("未知权限值 %s (用户 %s)", p, uid)

    def _save(self) -> None:
        """将权限数据持久化到 JSON 文件。"""
        self._storage.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, list[str]] = {
            uid: [p.value for p in perms]
            for uid, perms in self._permissions.items()
            if perms
        }
        self._storage.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# 搜索引擎
# ---------------------------------------------------------------------------


class KnowledgeSearchEngine:
    """知识库搜索引擎。

    从 knowledge/articles/ 目录加载全部 JSON 文章，支持按关键词、
    标签、日期范围、分类过滤，并按指定字段排序。

    Attributes:
        _knowledge_dir: 文章 JSON 文件目录。
        _articles: 内存中缓存的全部文章 dict 列表。
    """

    def __init__(self, knowledge_dir: str = "knowledge/articles") -> None:
        """初始化搜索引擎。

        Args:
            knowledge_dir: 知识条目 JSON 文件所在目录。
        """
        self._knowledge_dir = Path(knowledge_dir)
        self._articles: list[dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def search(
        self,
        keyword: str | None = None,
        tags: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        category: str | None = None,
        limit: int = 10,
        sort_by: str = "relevance_score",
    ) -> list[SearchResult]:
        """搜索知识条目。

        Args:
            keyword: 关键词，在标题/摘要/标签中模糊匹配。
            tags: 标签列表，文章至少包含其中之一即命中。
            date_from: 起始日期 YYYY-MM-DD（含）。
            date_to: 结束日期 YYYY-MM-DD（含）。
            category: 分类精确匹配。
            limit: 返回结果上限。
            sort_by: 排序字段（relevance_score / date）。

        Returns:
            SearchResult 列表。
        """
        results: list[dict[str, Any]] = []

        for article in self._articles:
            if not self._match_article(article, keyword, tags, date_from, date_to, category):
                continue
            results.append(article)

        if sort_by == "date":
            results.sort(key=self._extract_date, reverse=True)
        else:
            results.sort(key=self._extract_score, reverse=True)

        top = results[:limit]
        return [self._to_result(a) for a in top]

    def get_today(self, limit: int = 10) -> list[SearchResult]:
        """获取今日知识条目。

        Args:
            limit: 返回条数上限。

        Returns:
            SearchResult 列表。
        """
        today = date.today().isoformat()
        return self.search(date_from=today, date_to=today, limit=limit, sort_by="relevance_score")

    def get_top(self, days: int = 7, limit: int = 10) -> list[SearchResult]:
        """获取近期热门知识条目。

        Args:
            days: 回溯天数，默认 7 天。
            limit: 返回条数上限。

        Returns:
            SearchResult 列表。
        """
        date_from = (date.today() - timedelta(days=days)).isoformat()
        return self.search(date_from=date_from, limit=limit, sort_by="relevance_score")

    def reload(self) -> None:
        """重新加载文章数据。"""
        self._articles.clear()
        self._load()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """从 knowledge/articles/ 加载全部 JSON 文章。"""
        if not self._knowledge_dir.is_dir():
            logger.warning("知识条目目录不存在: %s", self._knowledge_dir)
            return
        for fp in sorted(self._knowledge_dir.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and "id" in data:
                self._articles.append(data)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "id" in item:
                        self._articles.append(item)

    def _match_article(
        self,
        article: dict[str, Any],
        keyword: str | None,
        tags: list[str] | None,
        date_from: str | None,
        date_to: str | None,
        category: str | None,
    ) -> bool:
        """判断文章是否匹配所有过滤条件。"""
        if keyword:
            if not self._keyword_match(article, keyword):
                return False
        if tags:
            if not self._tags_match(article, tags):
                return False
        if date_from or date_to:
            if not self._date_match(article, date_from, date_to):
                return False
        if category:
            if str(article.get("category", "")).lower() != category.lower():
                return False
        return True

    @staticmethod
    def _keyword_match(article: dict[str, Any], keyword: str) -> bool:
        """模糊关键词匹配。"""
        kw = keyword.lower()
        search_fields = [
            article.get("title", ""),
            article.get("summary", ""),
            " ".join(article.get("tags", [])),
        ]
        return any(kw in str(f).lower() for f in search_fields)

    @staticmethod
    def _tags_match(article: dict[str, Any], tags: list[str]) -> bool:
        """标签 OR 匹配：文章至少包含一个目标标签。"""
        article_tags = {str(t).lower() for t in article.get("tags", [])}
        return bool(article_tags & {t.lower() for t in tags})

    @staticmethod
    def _date_match(
        article: dict[str, Any],
        date_from: str | None,
        date_to: str | None,
    ) -> bool:
        """日期范围匹配。"""
        art_date = KnowledgeSearchEngine._extract_date_str(article)
        if not art_date:
            return False
        if date_from and art_date < date_from:
            return False
        if date_to and art_date > date_to:
            return False
        return True

    @staticmethod
    def _extract_date_str(article: dict[str, Any]) -> str:
        """从文章字典提取日期字符串（前 10 位）。"""
        for key in ("created_at", "updated_at", "collected_at", "fetched_at", "analyzed_at"):
            val = article.get(key)
            if val and isinstance(val, str) and len(val) >= 10:
                return val[:10]
        # 尝试从 id 中解析日期（格式: YYYY-MM-DD-...）
        aid = article.get("id", "")
        if isinstance(aid, str) and len(aid) >= 10:
            return aid[:10]
        return ""

    @staticmethod
    def _extract_score(article: dict[str, Any]) -> float:
        """提取相关度评分。"""
        raw = article.get("relevance_score")
        if raw is None:
            raw = article.get("score")
        return float(raw) if raw is not None else 0.0

    @staticmethod
    def _extract_date(article: dict[str, Any]) -> str:
        """提取排序用日期。"""
        return KnowledgeSearchEngine._extract_date_str(article) or "0000-00-00"

    @staticmethod
    def _to_result(article: dict[str, Any]) -> SearchResult:
        """将原始 dict 转为 SearchResult。"""
        return SearchResult(
            id=str(article.get("id", "")),
            title=str(article.get("title", "Untitled")),
            summary=str(article.get("summary", "")),
            tags=[str(t) for t in article.get("tags", [])],
            category=str(article.get("category", "")),
            relevance_score=KnowledgeSearchEngine._extract_score(article),
            source=str(article.get("source", "unknown")),
            source_url=str(article.get("source_url") or article.get("url") or ""),
            date=KnowledgeSearchEngine._extract_date_str(article),
        )


# ---------------------------------------------------------------------------
# 订阅管理器
# ---------------------------------------------------------------------------


class SubscriptionManager:
    """用户订阅管理器。

    每个用户可以订阅一组关键词和标签，持久化到 JSON 文件。

    Attributes:
        _storage: 订阅数据文件路径。
        _subs: user_id → {"keywords": [...], "tags": [...]} 映射。
    """

    def __init__(self, storage_path: str = "knowledge/subscriptions.json") -> None:
        """初始化订阅管理器。

        Args:
            storage_path: 订阅 JSON 文件路径。
        """
        self._storage = Path(storage_path)
        self._subs: dict[str, dict[str, list[str]]] = {}
        self._load()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def add(self, user_id: str, keywords: list[str] | None = None,
            tags: list[str] | None = None) -> bool:
        """添加或更新用户订阅。

        Args:
            user_id: 用户标识。
            keywords: 订阅关键词列表。
            tags: 订阅标签列表。

        Returns:
            True 表示新增订阅，False 表示更新已有订阅。
        """
        is_new = user_id not in self._subs
        self._subs[user_id] = {
            "keywords": list(keywords or []),
            "tags": list(tags or []),
        }
        self._save()
        return is_new

    def remove(self, user_id: str) -> bool:
        """移除用户订阅。

        Args:
            user_id: 用户标识。

        Returns:
            True 表示成功移除，False 表示用户无订阅记录。
        """
        if user_id not in self._subs:
            return False
        del self._subs[user_id]
        self._save()
        return True

    def get(self, user_id: str) -> dict[str, list[str]] | None:
        """获取用户订阅信息。

        Args:
            user_id: 用户标识。

        Returns:
            dict {"keywords": [...], "tags": [...]} 或 None。
        """
        return self._subs.get(user_id)

    def list_all(self) -> dict[str, dict[str, list[str]]]:
        """列出全部订阅。

        Returns:
            user_id → 订阅详情映射。
        """
        return dict(self._subs)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """从 JSON 文件加载订阅数据。"""
        if not self._storage.exists():
            return
        try:
            data = json.loads(self._storage.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("订阅文件 %s 读取失败: %s", self._storage, exc)
            return
        for uid, sub in data.items():
            if isinstance(sub, dict):
                self._subs[uid] = {
                    "keywords": list(sub.get("keywords", [])),
                    "tags": list(sub.get("tags", [])),
                }

    def _save(self) -> None:
        """将订阅数据持久化到 JSON 文件。"""
        self._storage.parent.mkdir(parents=True, exist_ok=True)
        self._storage.write_text(
            json.dumps(self._subs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# 知识库机器人主入口
# ---------------------------------------------------------------------------


class KnowledgeBot:
    """知识库交互机器人。

    整合搜索引擎、订阅管理器、权限管理器，提供统一的
    handle_message(user_id, text) -> str 入口。

    Attributes:
        _search: 搜索引擎实例。
        _subs: 订阅管理器实例。
        _perms: 权限管理器实例。
    """

    def __init__(
        self,
        knowledge_dir: str = "knowledge/articles",
        perm_path: str = "knowledge/permissions.json",
        sub_path: str = "knowledge/subscriptions.json",
    ) -> None:
        """初始化机器人。

        Args:
            knowledge_dir: 知识条目目录。
            perm_path: 权限存储文件路径。
            sub_path: 订阅存储文件路径。
        """
        self._search = KnowledgeSearchEngine(knowledge_dir)
        self._subs = SubscriptionManager(sub_path)
        self._perms = PermissionManager(perm_path)

    # ------------------------------------------------------------------
    # 统一入口
    # ------------------------------------------------------------------

    def handle_message(self, user_id: str, text: str) -> str:
        """处理用户消息的统一入口。

        根据意图分发到对应处理器，并在需要时进行权限检查。

        Args:
            user_id: 用户标识。
            text: 用户输入文本。

        Returns:
            格式化回复文本。
        """
        intent, args = recognize_intent(text)

        # 确保用户至少有 READ 权限（首次交互自动授予）
        self._perms.grant_default_read(user_id)

        handlers = {
            Intent.SEARCH: self._handle_search,
            Intent.TODAY: self._handle_today,
            Intent.TOP: self._handle_top,
            Intent.SUBSCRIBE: self._handle_subscribe,
            Intent.UNSUBSCRIBE: self._handle_unsubscribe,
            Intent.MYSUBS: self._handle_mysubs,
            Intent.HELP: self._handle_help,
            Intent.UNKNOWN: self._handle_unknown,
        }

        handler = handlers.get(intent, self._handle_unknown)
        try:
            return handler(user_id, args)
        except Exception as exc:
            logger.exception("处理消息异常 user=%s intent=%s", user_id, intent)
            return f"处理请求时发生异常: {exc}"

    # ------------------------------------------------------------------
    # 子处理器
    # ------------------------------------------------------------------

    def _handle_search(self, user_id: str, args: str) -> str:
        """处理搜索请求（/search）。

        权限: READ。
        支持参数: 关键词、标签（#tag）、分类（@category）、
                 日期范围（from: / to:）。
        """
        _ = user_id
        params = self._parse_search_args(args)
        keyword = params.get("keyword")
        tags = params.get("tags")
        category = params.get("category")
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        limit = int(params.get("limit", 10))

        if not keyword and not tags and not category and not date_from and not date_to:
            return "请提供搜索条件，例如: /search langchain\n" \
                   "支持: 关键词  #标签  @分类  from:日期  to:日期"

        results = self._search.search(
            keyword=keyword,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
            category=category,
            limit=limit,
        )

        if not results:
            return "未找到匹配的知识条目。"

        return self._format_search_results(results, keyword, tags, category)

    def _handle_today(self, user_id: str, args: str) -> str:
        """处理今日简报请求（/today）。

        权限: READ。
        """
        _ = user_id
        limit = int(args.strip()) if args.strip().isdigit() else 10
        results = self._search.get_today(limit=limit)

        if not results:
            today_str = date.today().isoformat()
            # 如果没有今日数据，回退到最新日期
            all_recent = self._search.search(limit=limit, sort_by="date")
            if all_recent:
                latest_date = all_recent[0].date
                results = self._search.search(
                    date_from=latest_date, date_to=latest_date, limit=limit,
                )
                header = f"📰 今日 ({today_str}) 暂无新增\n" \
                         f"📌 展示最新日期 ({latest_date}) Top {len(results)}:\n\n"
            else:
                return f"📭 {today_str} 暂无知识条目"
        else:
            header = f"📰 今日简报 ({date.today().isoformat()})  Top {len(results)}:\n\n"

        return header + self._format_results_brief(results)

    def _handle_top(self, user_id: str, args: str) -> str:
        """处理热榜请求（/top）。

        权限: READ。
        支持参数: 天数（默认 7）。
        """
        _ = user_id
        parts = args.strip().split()
        days = 7
        limit = 10
        if len(parts) >= 1 and parts[0].isdigit():
            days = int(parts[0])
        if len(parts) >= 2 and parts[1].isdigit():
            limit = int(parts[1])

        days = max(1, min(days, 30))
        limit = max(1, min(limit, 20))

        results = self._search.get_top(days=days, limit=limit)

        if not results:
            return f"📭 近 {days} 天内暂无知识条目"

        header = f"🔥 近 {days} 天热榜  Top {len(results)}:\n\n"
        return header + self._format_results_brief(results)

    def _handle_subscribe(self, user_id: str, args: str) -> str:
        """处理订阅请求（/subscribe）。

        权限: WRITE。
        """
        if not self._perms.has_permission(user_id, Permission.WRITE):
            return "❌ 您没有订阅权限（需要 WRITE 权限）"

        params = self._parse_search_args(args)
        keywords = [params["keyword"]] if params.get("keyword") else []
        tags = params.get("tags", [])
        category = params.get("category", "")

        if not keywords and not tags and not category:
            return "请提供订阅条件，例如: /subscribe langchain #agent\n" \
                   "支持: 关键词  #标签  @分类"

        # 将 category 也作为 tag 加入
        if category:
            tags = list(tags) + [category]

        is_new = self._subs.add(user_id, keywords=keywords, tags=tags)
        keyword_str = ", ".join(keywords) if keywords else "无"
        tag_str = ", ".join(tags) if tags else "无"
        action = "已创建" if is_new else "已更新"

        return f"✅ 订阅 {action}\n" \
               f"- 关键词: {keyword_str}\n" \
               f"- 标签/分类: {tag_str}"

    def _handle_unsubscribe(self, user_id: str, args: str) -> str:
        """处理取消订阅请求（/unsubscribe）。

        权限: WRITE。
        """
        _ = args
        if not self._perms.has_permission(user_id, Permission.WRITE):
            return "❌ 您没有取消订阅权限（需要 WRITE 权限）"

        removed = self._subs.remove(user_id)
        if removed:
            return "✅ 已取消全部订阅"
        return "ℹ️ 您当前没有订阅记录"

    def _handle_mysubs(self, user_id: str, args: str) -> str:
        """处理查看订阅请求（/mysubs）。

        权限: READ。
        """
        _ = args
        sub = self._subs.get(user_id)
        if not sub or (not sub["keywords"] and not sub["tags"]):
            return "ℹ️ 您当前没有订阅。\n" \
                   "使用 /subscribe 关键词 #标签 来创建订阅"

        lines = ["📋 我的订阅:"]
        if sub["keywords"]:
            lines.append(f"  关键词: {', '.join(sub['keywords'])}")
        if sub["tags"]:
            lines.append(f"  标签: {', '.join(sub['tags'])}")
        return "\n".join(lines)

    def _handle_help(self, user_id: str, args: str) -> str:
        """处理帮助请求（/help）。

        权限: 无。
        """
        _ = user_id
        _ = args
        return (
            "🤖 **AI 知识库助手** 使用说明\n\n"
            "**命令列表**\n"
            "  /search <关键词> [#标签] [@分类] — 搜索知识条目\n"
            "    参数: from:日期  to:日期  #tag  @category\n"
            "  /today [数量] — 查看今日简报\n"
            "  /top [天数] [数量] — 查看近期热榜\n"
            "  /subscribe <关键词> [#标签] — 订阅话题\n"
            "  /unsubscribe — 取消全部订阅\n"
            "  /mysubs — 查看我的订阅\n"
            "  /help — 显示帮助\n\n"
            "**示例**\n"
            "  /search langchain #agent\n"
            "  /search @agent-framework from:2026-05-01\n"
            "  /today 5\n"
            "  /top 7 10\n"
            "  /subscribe LLM #llm @research\n"
        )

    def _handle_unknown(self, user_id: str, args: str) -> str:
        """处理未知意图。

        权限: READ。
        """
        _ = user_id
        _ = args
        return (
            "未识别到有效指令。\n"
            "请使用 /help 查看可用命令，或直接输入关键词进行搜索。"
        )

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_search_args(args: str) -> dict[str, Any]:
        """解析搜索参数字符串。

        提取关键词、#tag、@category、from: / to: 日期、limit:。

        Args:
            args: 原始参数字符串。

        Returns:
            参数字典。
        """
        params: dict[str, Any] = {}
        tags: list[str] = []
        keywords: list[str] = []

        # 提取 from: / to: / limit:
        date_from_match = re.search(r"from\s*:\s*(\S+)", args)
        date_to_match = re.search(r"to\s*:\s*(\S+)", args)
        limit_match = re.search(r"limit\s*:\s*(\d+)", args, re.IGNORECASE)

        if date_from_match:
            params["date_from"] = date_from_match.group(1).rstrip(",")
        if date_to_match:
            params["date_to"] = date_to_match.group(1).rstrip(",")
        if limit_match:
            params["limit"] = limit_match.group(1)

        # 移除已匹配的 from:/to:/limit: 子句
        remaining = re.sub(r"(from|to|limit)\s*:\s*\S+", "", args, flags=re.IGNORECASE)

        # 分词提取 #tag 和 @category
        for token in remaining.split():
            token = token.rstrip(",.;，。；、")
            if token.startswith("#") and len(token) > 1:
                tags.append(token[1:])
            elif token.startswith("@") and len(token) > 1:
                params["category"] = token[1:]
            elif token:
                keywords.append(token)

        if keywords:
            params["keyword"] = " ".join(keywords)
        if tags:
            params["tags"] = tags

        return params

    @staticmethod
    def _format_search_results(
        results: list[SearchResult],
        keyword: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
    ) -> str:
        """格式化搜索结果。

        Args:
            results: SearchResult 列表。
            keyword: 搜索关键词（用于显示）。
            tags: 搜索标签（用于显示）。
            category: 搜索分类（用于显示）。

        Returns:
            格式化文本。
        """
        cond_parts = []
        if keyword:
            cond_parts.append(f"关键词={keyword}")
        if tags:
            cond_parts.append(f"标签={', '.join(tags)}")
        if category:
            cond_parts.append(f"分类={category}")
        cond_str = " / ".join(cond_parts) if cond_parts else ""

        header = f"🔍 搜索" + (f" ({cond_str})" if cond_str else "") + \
                 f" — 共 {len(results)} 条:\n\n"

        lines = [header]
        for i, r in enumerate(results, 1):
            score_icon = "🟢" if r.relevance_score >= 0.8 else \
                         ("🟡" if r.relevance_score >= 0.6 else "🔴")
            tag_str = ", ".join(r.tags[:5]) if r.tags else "—"
            url_str = f"\n    原文: {r.source_url}" if r.source_url else ""

            lines.append(
                f"{i}. {score_icon} [{r.category}] {r.title}\n"
                f"   日期: {r.date}  |  相关度: {r.relevance_score:.2f}\n"
                f"   标签: {tag_str}\n"
                f"   {r.summary[:120]}{'...' if len(r.summary) > 120 else ''}"
                f"{url_str}\n"
            )

        return "\n".join(lines)

    @staticmethod
    def _format_results_brief(results: list[SearchResult]) -> str:
        """格式化简报结果。

        Args:
            results: SearchResult 列表。

        Returns:
            格式化文本。
        """
        lines: list[str] = []
        for i, r in enumerate(results, 1):
            score_icon = "🟢" if r.relevance_score >= 0.8 else \
                         ("🟡" if r.relevance_score >= 0.6 else "🔴")
            url_str = f"  🔗 {r.source_url}" if r.source_url else ""
            lines.append(
                f"{i}. {score_icon} [{r.category}] {r.title}\n"
                f"   相关度: {r.relevance_score:.2f}  |  {r.date}"
                f"{url_str}\n"
            )
        return "\n".join(lines)
