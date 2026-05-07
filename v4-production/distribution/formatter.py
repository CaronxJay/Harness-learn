#!/usr/bin/env python3
"""知识条目格式化模块。

提供将单篇知识条目（v3 LangGraph Organizer 节点产出）转换为
Markdown、Telegram MarkdownV2、飞书交互式卡片三种格式的纯函数，
以及从 knowledge/articles/ 目录读取当日文章并生成每日简报的工具。
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_TELEGRAM_SPECIAL = r"_*[]()~`>#+-=|{}.!"
_TELEGRAM_ESCAPE_RE = re.compile(f"([{re.escape(_TELEGRAM_SPECIAL)}])")

_RELEVANCE_THRESHOLD_GREEN = 0.8
_RELEVANCE_THRESHOLD_YELLOW = 0.6


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------


def _escape_telegram(text: str) -> str:
    """转义 Telegram MarkdownV2 特殊字符，在每个特殊字符前加反斜杠。

    Args:
        text: 原始文本。

    Returns:
        转义后的文本。
    """
    return _TELEGRAM_ESCAPE_RE.sub(r"\\\1", text)


def _score_emoji(score: float) -> str:
    """根据相关度评分返回视觉指示符。

    >= 0.8 → 🟢（高）
    >= 0.6 → 🟟（中）
     其他  → 🔴（低）

    Args:
        score: 相关度评分。

    Returns:
        单个 emoji 指示符。
    """
    if score >= _RELEVANCE_THRESHOLD_GREEN:
        return "\U0001f7e2"  # 🟢
    if score >= _RELEVANCE_THRESHOLD_YELLOW:
        return "\U0001f7e1"  # 🟟
    return "\U0001f534"  # 🔴


def _score_feishu_color(score: float) -> str:
    """根据相关度评分返回飞书卡片 header 模板颜色。

    >= 0.8 → green
    >= 0.6 → yellow
     其他  → red

    Args:
        score: 相关度评分。

    Returns:
        "green" / "yellow" / "red"。
    """
    if score >= _RELEVANCE_THRESHOLD_GREEN:
        return "green"
    if score >= _RELEVANCE_THRESHOLD_YELLOW:
        return "yellow"
    return "red"


def _get_date_str(article: dict[str, Any]) -> str:
    """从文章字典中提取日期字符串（前 10 位）。

    兼容多种时间字段：collected_at / created_at / fetched_at / analyzed_at。

    Args:
        article: 知识条目字典。

    Returns:
        日期字符串 YYYY-MM-DD，或 "unknown"。
    """
    for key in ("collected_at", "created_at", "fetched_at", "analyzed_at"):
        val = article.get(key)
        if val and isinstance(val, str) and len(val) >= 10:
            return val[:10]
    return "unknown"


def _get_url(article: dict[str, Any]) -> str:
    """从文章字典中提取原文链接。

    兼容两种字段名：url / source_url。

    Args:
        article: 知识条目字典。

    Returns:
        URL 字符串，或空字符串。
    """
    return str(article.get("url") or article.get("source_url") or "")


def _get_score(article: dict[str, Any]) -> float:
    """从文章字典中提取相关度评分。

    兼容两种字段名：relevance_score / score。

    Args:
        article: 知识条目字典。

    Returns:
        相关度评分浮点数，缺失时返回 0.0。
    """
    raw = article.get("relevance_score") or article.get("score")
    if raw is None:
        return 0.0
    return float(raw)


def _get_tags(article: dict[str, Any]) -> str:
    """从文章字典中提取标签并以逗号分隔拼接。

    Args:
        article: 知识条目字典。

    Returns:
        逗号分隔的标签字符串。
    """
    tags: list[str] = article.get("tags", [])
    if not tags:
        return ""
    return ", ".join(str(t) for t in tags)


# ---------------------------------------------------------------------------
# 公开格式化函数
# ---------------------------------------------------------------------------


def json_to_markdown(article: dict[str, Any]) -> str:
    """将单篇知识条目转换为 Markdown 文本。

    包含标题、来源、日期、相关性评分（带颜色 emoji）、标签、
    摘要、关键洞察和原文链接。

    Args:
        article: 知识条目字典，需包含 id、title、source、summary、
                 relevance_score 等字段。

    Returns:
        Markdown 格式化字符串。
    """
    title = article.get("title", "Untitled")
    source = article.get("source", "unknown")
    date_str = _get_date_str(article)
    score = _get_score(article)
    emoji = _score_emoji(score)
    tags = _get_tags(article)
    summary = article.get("summary", "")
    url = _get_url(article)
    insight = article.get("key_insight", "")
    category = article.get("category", "")

    lines: list[str] = [
        f"## {title}",
        "",
        f"- **来源**: {source}",
        f"- **日期**: {date_str}",
        f"- **相关性**: {emoji} {score:.2f}",
    ]

    if tags:
        lines.append(f"- **标签**: {tags}")
    if category:
        lines.append(f"- **分类**: {category}")

    lines.append("")
    lines.append(summary)

    if insight:
        lines.append("")
        lines.append(f"> 💡 {insight}")

    if url:
        lines.append("")
        lines.append(f"[原文链接]({url})")

    return "\n".join(lines)


def json_to_telegram(article: dict[str, Any]) -> str:
    """将单篇知识条目转换为 Telegram MarkdownV2 文本。

    对标题、摘要等文本中的 Telegram 特殊字符进行转义，标签中
    空格替换为下划线。

    Args:
        article: 知识条目字典。

    Returns:
        Telegram MarkdownV2 格式化字符串。
    """
    title = _escape_telegram(article.get("title", "Untitled"))
    source = _escape_telegram(article.get("source", "unknown"))
    date_str = _escape_telegram(_get_date_str(article))
    score = _get_score(article)
    emoji = _score_emoji(score)
    summary = _escape_telegram(article.get("summary", ""))
    url = _get_url(article)
    insight = article.get("key_insight", "")
    insight_esc = _escape_telegram(insight) if insight else ""

    # 标签：空格替换为下划线
    raw_tags: list[str] = article.get("tags", [])
    tags_display = ", ".join(
        f"#{str(t).replace(' ', '_')}" for t in raw_tags
    )

    # 标题优先以链接形式展示
    if url:
        title_line = f"[{title}]({_escape_telegram(url)})"
    else:
        title_line = f"*{title}*"

    lines: list[str] = [
        title_line,
        "",
    ]

    if summary:
        lines.append(summary)
        lines.append("")

    lines.extend([
        f"{emoji} 相关性: {score:.2f}  |  来源: {source}  |  日期: {date_str}",
    ])

    if tags_display:
        lines.append(f"标签: {tags_display}")

    if insight_esc:
        lines.append(f"💡 {insight_esc}")

    return "\n".join(lines)


def json_to_feishu(article: dict[str, Any]) -> dict[str, Any]:
    """将单篇知识条目转换为飞书交互式卡片 dict。

    msg_type 固定为 interactive，header 标题模板颜色按
    relevance_score 三档染色（green / yellow / red）。

    Args:
        article: 知识条目字典。

    Returns:
        飞书消息体 dict，可直接 JSON 序列化后发送。
    """
    title = article.get("title", "Untitled")
    source = article.get("source", "unknown")
    date_str = _get_date_str(article)
    score = _get_score(article)
    emoji = _score_emoji(score)
    color = _score_feishu_color(score)
    summary = article.get("summary", "")
    tags = _get_tags(article)
    url = _get_url(article)
    insight = article.get("key_insight", "")
    category = article.get("category", "")

    # 正文富文本
    body_lines: list[str] = []
    body_lines.append(f"**来源**: {source}")
    body_lines.append(f"**日期**: {date_str}")
    body_lines.append(f"**相关性**: {emoji} {score:.2f}")
    if category:
        body_lines.append(f"**分类**: {category}")
    if tags:
        body_lines.append(f"**标签**: {tags}")
    if summary:
        body_lines.append("")
        body_lines.append(summary)
    if insight:
        body_lines.append("")
        body_lines.append(f"💡 {insight}")

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(body_lines),
            },
        },
    ]

    if url:
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": "查看原文",
                    },
                    "type": "primary",
                    "url": url,
                },
            ],
        })

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "elements": [
            {
                "tag": "plain_text",
                "content": "AI Knowledge Base · Daily Digest",
            },
        ],
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title,
                    "template": color,
                },
            },
            "elements": elements,
        },
    }


def json_to_qq(article: dict[str, Any]) -> str:
    """将单篇知识条目转换为 QQ 文本。

    使用与 Telegram 相同的特殊字符转义规则，标签空格替换为
    下划线。QQ 频道 / 群机器人适用。

    Args:
        article: 知识条目字典。

    Returns:
        QQ 格式化字符串。
    """
    title = _escape_telegram(article.get("title", "Untitled"))
    source = _escape_telegram(article.get("source", "unknown"))
    date_str = _escape_telegram(_get_date_str(article))
    score = _get_score(article)
    emoji = _score_emoji(score)
    summary = _escape_telegram(article.get("summary", ""))
    url = _get_url(article)
    insight = article.get("key_insight", "")
    insight_esc = _escape_telegram(insight) if insight else ""

    raw_tags: list[str] = article.get("tags", [])
    tags_display = "  ".join(
        f"[#{str(t).replace(' ', '_')}]" for t in raw_tags
    )

    if url:
        title_line = f"📌 [{title}]({_escape_telegram(url)})"
    else:
        title_line = f"📌 {title}"

    lines: list[str] = [title_line]

    if summary:
        lines.append("")
        lines.append(summary)

    lines.append("")
    lines.append(f"{emoji} 相关性: {score:.2f}  |  来源: {source}  |  📅 {date_str}")

    if tags_display:
        lines.append(f"🏷 {tags_display}")

    if insight_esc:
        lines.append(f"💡 {insight_esc}")

    return "\n".join(lines)


def json_to_wechat(article: dict[str, Any]) -> str:
    """将单篇知识条目转换为微信文本。

    适用于企业微信机器人 Markdown 消息，使用与 Telegram 相同的
    特殊字符转义规则，标签空格替换为下划线。

    Args:
        article: 知识条目字典。

    Returns:
        微信格式化字符串。
    """
    title = _escape_telegram(article.get("title", "Untitled"))
    source = _escape_telegram(article.get("source", "unknown"))
    date_str = _escape_telegram(_get_date_str(article))
    score = _get_score(article)
    emoji = _score_emoji(score)
    summary = _escape_telegram(article.get("summary", ""))
    url = _get_url(article)
    insight = article.get("key_insight", "")
    insight_esc = _escape_telegram(insight) if insight else ""

    raw_tags: list[str] = article.get("tags", [])
    tags_display = "、".join(
        str(t).replace(" ", "_") for t in raw_tags
    )

    if url:
        title_line = f"[{title}]({_escape_telegram(url)})"
    else:
        title_line = f"**{title}**"

    lines: list[str] = [title_line]

    if summary:
        lines.append(f"> {summary}")

    lines.append("")
    lines.append(f"{emoji} 相关性: {score:.1f} | 来源: {source} | {date_str}")

    if tags_display:
        lines.append(f"标签: {tags_display}")

    if insight_esc:
        lines.append(f"> 💡 {insight_esc}")

    return "\n".join(lines)


def generate_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date_str: str | None = None,
    top_n: int = 5,
) -> dict[str, str | list[dict[str, Any]]]:
    """生成当日知识简报，包含 Markdown、Telegram、飞书、QQ、微信五种格式。

    从 knowledge_dir 目录下读取文件名以 {date}- 开头
    的 JSON 文件，按 relevance_score 降序排列取 Top N
    条目，分别生成五种格式的聚合内容。

    Args:
        knowledge_dir: 知识条目 JSON 文件所在目录，默认 "knowledge/articles"。
        date_str: 日期字符串 YYYY-MM-DD，默认今天。
        top_n: 取 Top N 条，默认 5。

    Returns:
        dict: {"markdown": str, "telegram": str, "feishu": list[dict],
               "qq": str, "wechat": str}
              当日无文章时返回 {"markdown": "📭 ...", "telegram": "...",
              "feishu": [], "qq": "...", "wechat": "..."}
    """
    if date_str is None:
        date_str = date.today().isoformat()

    base = Path(knowledge_dir)
    pattern = f"{date_str}-*.json"
    files = sorted(base.glob(pattern))

    articles: list[dict[str, Any]] = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if isinstance(data, dict) and "id" in data:
            articles.append(data)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "id" in item:
                    articles.append(item)

    if not articles:
        empty_msg = f"📭 {date_str} 暂无新增知识条目"
        return {
            "markdown": empty_msg,
            "telegram": empty_msg,
            "feishu": [],
            "qq": empty_msg,
            "wechat": empty_msg,
        }

    articles.sort(key=lambda a: _get_score(a), reverse=True)
    top_articles = articles[:top_n]

    # 生成汇总头部
    total = len(articles)
    header_md = f"# AI 知识库 · 日报 ({date_str})\n\n共采集 {total} 篇，以下是相关度最高的 {len(top_articles)} 篇：\n\n---\n"
    header_tg = _escape_telegram(
        f"📰 AI 知识库 · 日报 ({date_str})\n\n"
        f"共采集 {total} 篇，以下是相关度最高的 {len(top_articles)} 篇：\n"
    )
    header_qq = (
        f"📰 AI 知识库 · 日报 ({date_str})\n"
        f"共采集 {total} 篇，以下是相关度最高的 {len(top_articles)} 篇：\n"
    )
    header_wechat = _escape_telegram(
        f"📰 AI 知识库 · 日报 ({date_str})\n"
        f"共采集 {total} 篇，以下是相关度最高的 {len(top_articles)} 篇：\n"
    )

    # Markdown 聚合
    md_parts = [header_md]
    for article in top_articles:
        md_parts.append(json_to_markdown(article))
        md_parts.append("\n---\n")
    markdown_output = "\n".join(md_parts)

    # Telegram 聚合
    tg_parts = [header_tg]
    for i, article in enumerate(top_articles, 1):
        tg_parts.append(f"\n{'━' * 20} {i} {'━' * 20}\n")
        tg_parts.append(json_to_telegram(article))
    telegram_output = "\n".join(tg_parts)

    # QQ 聚合
    qq_parts = [header_qq]
    for i, article in enumerate(top_articles, 1):
        qq_parts.append(f"\n{'━' * 20} {i} {'━' * 20}\n")
        qq_parts.append(json_to_qq(article))
    qq_output = "\n".join(qq_parts)

    # 微信聚合
    wechat_parts = [header_wechat]
    for i, article in enumerate(top_articles, 1):
        wechat_parts.append(f"\n{'━' * 20} {i} {'━' * 20}\n")
        wechat_parts.append(json_to_wechat(article))
    wechat_output = "\n".join(wechat_parts)

    # 飞书聚合
    feishu_cards = [json_to_feishu(article) for article in top_articles]

    return {
        "markdown": markdown_output,
        "telegram": telegram_output,
        "feishu": feishu_cards,
        "qq": qq_output,
        "wechat": wechat_output,
    }
