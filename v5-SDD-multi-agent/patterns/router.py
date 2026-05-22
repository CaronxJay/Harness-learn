"""Router 路由模式

两层意图分类策略：
- 第一层：关键词快速匹配（零成本，不调 LLM）
- 第二层：LLM 分类兜底（处理模糊意图）

三种意图：
- github_search: 搜索 GitHub 项目
- knowledge_query: 查询本地知识库
- general_chat: 通用对话

使用方法：
    from patterns.router import route

    response = route("介绍一下 LangChain 框架")
"""

import json
import logging
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

# 配置日志
logger = logging.getLogger(__name__)

# 知识库索引路径
KNOWLEDGE_INDEX_PATH = Path(__file__).parent.parent / "knowledge" / "articles" / "index.json"


# ============================================================
# LLM 接口适配
# ============================================================

def chat(prompt: str, system_prompt: Optional[str] = None) -> tuple[str, object]:
    """调用 LLM

    Args:
        prompt: 用户输入
        system_prompt: 系统提示词

    Returns:
        (响应文本, usage) 元组
    """
    # 延迟导入，避免循环依赖
    from pipeline.model_client import chat_with_retry

    response = chat_with_retry(
        prompt=prompt,
        system_prompt=system_prompt,
    )
    return response.content, response.usage


def chat_json(prompt: str, system_prompt: Optional[str] = None) -> dict:
    """调用 LLM 并解析 JSON 响应

    Args:
        prompt: 用户输入
        system_prompt: 系统提示词

    Returns:
        解析后的字典
    """
    text, _ = chat(prompt, system_prompt)
    # 提取 JSON 内容
    text = text.strip()
    if text.startswith("```"):
        # 移除 markdown 代码块
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


# ============================================================
# 意图分类
# ============================================================

# 关键词映射表
KEYWORD_PATTERNS: dict[str, list[str]] = {
    "github_search": [
        "github", "开源", "项目", "仓库", "repo", "star", "trending",
        "代码库", "框架", "library", "库", "sdk", "工具",
    ],
    "knowledge_query": [
        "知识库", "笔记", "记录", "之前", "保存", "查一下",
        "找找", "记录", "笔记", "本地",
    ],
}


def classify_by_keywords(query: str) -> Optional[str]:
    """第一层：关键词快速匹配

    Args:
        query: 用户查询

    Returns:
        意图类型，无法匹配返回 None
    """
    query_lower = query.lower()

    # 统计各意图的匹配分数
    scores: dict[str, int] = {}
    for intent, keywords in KEYWORD_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return None

    # 返回得分最高的意图
    return max(scores, key=scores.get)


def classify_by_llm(query: str) -> str:
    """第二层：LLM 意图分类

    Args:
        query: 用户查询

    Returns:
        意图类型
    """
    system_prompt = """你是一个意图分类器。根据用户输入，判断其意图类型。

意图类型：
- github_search: 用户想搜索或了解 GitHub 上的开源项目、框架、工具
- knowledge_query: 用户想查询之前保存的知识、笔记、文章
- general_chat: 用户想进行一般性对话、提问、闲聊

请只返回意图类型名称，不要返回其他内容。"""

    try:
        result = chat_json(
            prompt=f"用户输入：{query}",
            system_prompt=system_prompt,
        )
        intent = result.get("intent", "general_chat")
        if intent in ("github_search", "knowledge_query", "general_chat"):
            return intent
        return "general_chat"
    except Exception as e:
        logger.warning(f"LLM 意图分类失败: {e}")
        return "general_chat"


def classify_intent(query: str) -> str:
    """两层意图分类

    Args:
        query: 用户查询

    Returns:
        意图类型
    """
    # 第一层：关键词快速匹配
    intent = classify_by_keywords(query)
    if intent:
        logger.info(f"关键词匹配意图: {intent}")
        return intent

    # 第二层：LLM 分类兜底
    logger.info("关键词未匹配，使用 LLM 分类")
    intent = classify_by_llm(query)
    logger.info(f"LLM 分类意图: {intent}")
    return intent


# ============================================================
# 意图处理器
# ============================================================

def handle_github_search(query: str) -> str:
    """处理 GitHub 搜索意图

    调用 GitHub Search API 搜索相关项目。

    Args:
        query: 用户查询

    Returns:
        格式化的搜索结果
    """
    # 提取搜索关键词
    search_prompt = """从用户输入中提取 GitHub 搜索关键词。
只返回关键词，不要返回其他内容。

示例：
- "介绍一下 LangChain 框架" -> "LangChain"
- "有哪些好用的 Python Web 框架" -> "Python Web framework"
- "DeepSeek 相关项目" -> "DeepSeek"
"""
    try:
        keyword, _ = chat(query, search_prompt)
        keyword = keyword.strip().strip('"').strip("'")
    except Exception:
        keyword = query

    # URL 编码
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://api.github.com/search/repositories?q={encoded_keyword}&sort=stars&order=desc&per_page=5"

    logger.info(f"GitHub 搜索: {keyword}")

    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AI-Knowledge-Base",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        items = data.get("items", [])
        if not items:
            return f"未找到与「{keyword}」相关的 GitHub 项目。"

        # 格式化结果
        lines = [f"GitHub 搜索「{keyword}」的结果：\n"]
        for i, item in enumerate(items, 1):
            name = item.get("full_name", "")
            desc = item.get("description", "无描述")
            stars = item.get("stargazers_count", 0)
            lang = item.get("language", "未知")
            html_url = item.get("html_url", "")

            lines.append(f"{i}. **{name}** ⭐ {stars}")
            lines.append(f"   语言: {lang}")
            lines.append(f"   描述: {desc}")
            lines.append(f"   链接: {html_url}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"GitHub API 调用失败: {e}")
        return f"GitHub 搜索失败: {e}"


def handle_knowledge_query(query: str) -> str:
    """处理知识库查询意图

    从本地 knowledge/articles/index.json 检索相关文章。

    Args:
        query: 用户查询

    Returns:
        检索结果
    """
    if not KNOWLEDGE_INDEX_PATH.exists():
        return "知识库索引文件不存在，请先采集和分析内容。"

    try:
        with open(KNOWLEDGE_INDEX_PATH, "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception as e:
        logger.error(f"读取知识库索引失败: {e}")
        return f"读取知识库索引失败: {e}"

    articles = index.get("articles", [])
    if not articles:
        return "知识库为空，请先采集和分析内容。"

    # 简单关键词匹配
    query_lower = query.lower()
    matches = []
    for article in articles:
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()
        tags = [t.lower() for t in article.get("tags", [])]

        # 计算匹配分数
        score = 0
        if any(kw in title for kw in query_lower.split()):
            score += 3
        if any(kw in summary for kw in query_lower.split()):
            score += 2
        if any(kw in tag for tag in tags for kw in query_lower.split()):
            score += 1

        if score > 0:
            matches.append((score, article))

    if not matches:
        return f"未找到与「{query}」相关的知识条目。"

    # 按分数排序
    matches.sort(key=lambda x: x[0], reverse=True)

    # 格式化结果
    lines = [f"知识库检索「{query}」的结果：\n"]
    for i, (_, article) in enumerate(matches[:5], 1):
        title = article.get("title", "未知标题")
        summary = article.get("summary", "无摘要")
        source = article.get("source_url", "")
        tags = article.get("tags", [])

        lines.append(f"{i}. **{title}**")
        lines.append(f"   摘要: {summary[:100]}...")
        if tags:
            lines.append(f"   标签: {', '.join(tags[:5])}")
        if source:
            lines.append(f"   来源: {source}")
        lines.append("")

    return "\n".join(lines)


def handle_general_chat(query: str) -> str:
    """处理通用对话意图

    调用 LLM 直接回答。

    Args:
        query: 用户查询

    Returns:
        LLM 响应
    """
    system_prompt = """你是一个 AI 知识库助手。请用中文回答用户的问题。
回答要简洁、准确、有帮助。"""

    try:
        response, _ = chat(query, system_prompt)
        return response
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return f"抱歉，我无法回答这个问题: {e}"


# ============================================================
# 处理器映射
# ============================================================

HANDLERS: dict[str, Callable[[str], str]] = {
    "github_search": handle_github_search,
    "knowledge_query": handle_knowledge_query,
    "general_chat": handle_general_chat,
}


# ============================================================
# 统一入口
# ============================================================

def route(query: str) -> str:
    """路由用户查询到对应的处理器

    Args:
        query: 用户查询

    Returns:
        处理结果
    """
    logger.info(f"收到查询: {query}")

    # 意图分类
    intent = classify_intent(query)

    # 获取处理器
    handler = HANDLERS.get(intent)
    if handler is None:
        logger.warning(f"未知意图: {intent}，使用通用对话")
        handler = handle_general_chat

    # 执行处理
    result = handler(query)
    logger.info(f"处理完成，意图: {intent}")

    return result


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("=" * 60)
    logger.info("Router 路由模式测试")
    logger.info("=" * 60)

    # 测试用例
    test_queries = [
        "介绍一下 LangChain 框架",          # github_search
        "之前保存的笔记有哪些",              # knowledge_query
        "你好，请介绍一下自己",              # general_chat
        "有哪些好用的 Python Web 框架",      # github_search
        "帮我找找之前的记录",                # knowledge_query
    ]

    for query in test_queries:
        logger.info(f"\n{'=' * 40}")
        logger.info(f"查询: {query}")

        # 测试意图分类
        intent = classify_intent(query)
        logger.info(f"意图: {intent}")

        # 测试路由
        result = route(query)
        logger.info(f"结果:\n{result[:200]}...")

    logger.info("\n测试完成")
