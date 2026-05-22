"""LangGraph 工作流节点函数定义

5 个核心节点：collect → analyze → organize → review → save

每个节点是纯函数：接收 KBState，返回 dict（部分状态更新）。

使用方法：
    from workflows.nodes import (
        collect_node,
        analyze_node,
        organize_node,
        review_node,
        save_node,
    )
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tests.security import filter_output, sanitize_input
from workflows.model_client import accumulate_usage, chat, chat_json
from workflows.state import KBState

logger = logging.getLogger(__name__)


# ============================================================
# 1. collect_node: GitHub Search API 采集
# ============================================================

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
AI_KEYWORDS = [
    "llm",
    "large language model",
    "agent",
    "rag",
    "retrieval augmented",
    "langchain",
    "autogen",
    "crewai",
    "vector database",
    "embedding",
]


def collect_node(state: KBState) -> dict:
    """调用 GitHub Search API 采集 AI 相关仓库

    搜索最近一周创建或更新的热门 AI 项目，按 stars 排序。

    Args:
        state: 当前工作流状态

    Returns:
        {"sources": [...]} 部分状态更新
    """
    logger.info("[collect_node] 开始采集 GitHub Trending AI 项目")

    plan = state.get("plan") or {}
    per_source_limit = int(plan.get("per_source_limit", 10))

    sources: list[dict[str, Any]] = []
    query = " OR ".join(AI_KEYWORDS[:5])  # 取前 5 个关键词组合

    params = {
        "q": f"{query} created:>2025-01-01",
        "sort": "stars",
        "order": "desc",
        "per_page": per_source_limit,
    }

    url = f"{GITHUB_SEARCH_URL}?{urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-Knowledge-Base",
    }

    # 可选：GitHub Token 提升速率限制
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for repo in data.get("items", []):
            sources.append(
                {
                    "url": repo["html_url"],
                    "title": repo["full_name"],
                    "content": repo.get("description") or "",
                    "source_type": "github",
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language", ""),
                }
            )

        logger.info(f"[collect_node] 采集到 {len(sources)} 个仓库")

    except (HTTPError, URLError, json.JSONDecodeError) as e:
        logger.error(f"[collect_node] 采集失败: {e}")

    # 出 collect 之前对每条 source 的文本字段做清洗（防 Prompt 注入）
    cleaned_sources = []
    total_warnings = 0
    for s in sources:
        for field in ("title", "content"):
            if field in s and isinstance(s[field], str):
                cleaned, warnings = sanitize_input(s[field])
                s[field] = cleaned
                total_warnings += len(warnings)
                if warnings:
                    logger.warning(f"[Security] {s.get('url', '?')} {field} 检出注入模式：{warnings}")
        cleaned_sources.append(s)

    if total_warnings > 0:
        logger.warning(f"[Security] collect 阶段共拦截 {total_warnings} 处可疑输入")

    logger.info(f"[collect_node] 采集到 {len(cleaned_sources)} 条原始数据")
    return {"sources": cleaned_sources}


# ============================================================
# 2. analyze_node: LLM 分析生成摘要、标签、评分
# ============================================================

ANALYZE_SYSTEM_PROMPT = """你是一个 AI/LLM 领域的技术分析专家。
请对以下 GitHub 项目进行分析，输出严格 JSON 格式。

输出格式：
{
    "title": "项目简称",
    "summary": "中文摘要（100-200字，说明项目功能、技术栈、亮点）",
    "tags": ["tag1", "tag2", "tag3"],
    "tech_direction": "llm|agent|rag|infra|tool",
    "quality_score": 0.85,
    "use_case": "适用场景描述"
}

评分标准（quality_score 0-1）：
- 0.8+: 优秀，创新性强或实用价值高
- 0.6-0.8: 良好，有一定参考价值
- <0.6: 一般，价值有限

只输出 JSON，不要有其他内容。"""


def analyze_node(state: KBState) -> dict:
    """用 LLM 对每条数据生成中文摘要、标签、评分

    Args:
        state: 当前工作流状态，需要 sources 字段

    Returns:
        {"analyses": [...]} 部分状态更新
    """
    logger.info(f"[analyze_node] 开始分析 {len(state['sources'])} 条数据")

    analyses: list[dict[str, Any]] = []
    cost_tracker = state.get("cost_tracker", {})

    for i, source in enumerate(state["sources"]):
        prompt = f"""项目名称: {source['title']}
项目链接: {source['url']}
项目描述: {source['content']}
语言: {source.get('language', 'N/A')}
Stars: {source.get('stars', 'N/A')}"""

        try:
            result, usage = chat_json(prompt, ANALYZE_SYSTEM_PROMPT, node_name="analyze")
            accumulate_usage(cost_tracker, usage)

            # 补充元数据
            result["source_url"] = source["url"]
            result["source_type"] = source["source_type"]
            analyses.append(result)

            logger.debug(
                f"[analyze_node] ({i + 1}/{len(state['sources'])}) "
                f"分析完成: {result.get('title', 'N/A')}"
            )

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[analyze_node] 分析失败 [{source['title']}]: {e}")

    logger.info(f"[analyze_node] 分析完成，有效结果 {len(analyses)} 条")
    return {"analyses": analyses}


# ============================================================
# 3. organize_node: 过滤、去重、修正
# ============================================================

REVISE_SYSTEM_PROMPT = """你是一个技术内容编辑。
请根据审核反馈，对以下知识条目进行定向修改。

原始条目：
{article}

审核反馈：
{feedback}

要求：
1. 保留条目的核心信息
2. 根据反馈针对性修改（摘要/标签/分类等）
3. 输出修改后的完整 JSON（保持原格式）

只输出 JSON，不要有其他内容。"""


def organize_node(state: KBState) -> dict:
    """过滤低分条目、按 URL 去重、如有审核反馈则用 LLM 修正

    处理流程：
    1. 过滤 quality_score < 0.6 的低质量条目
    2. 按 source_url 去重（保留首次出现的）
    3. iteration > 0 且有 feedback 时，调用 LLM 做定向修改

    Args:
        state: 当前工作流状态，需要 analyses、iteration、review_feedback 字段

    Returns:
        {"articles": [...]} 部分状态更新
    """
    logger.info("[organize_node] 开始整理分析结果")

    analyses = state["analyses"]
    iteration = state.get("iteration", 0)
    feedback = state.get("review_feedback", "")
    cost_tracker = state.get("cost_tracker", {})

    plan = state.get("plan") or {}
    relevance_threshold = float(plan.get("relevance_threshold", 0.5))

    # Step 1: 过滤低分条目
    filtered = [a for a in analyses if a.get("quality_score", 0) >= relevance_threshold]
    logger.info(
        f"[organize_node] 过滤低分: {len(analyses)} -> {len(filtered)} "
        f"(移除 {len(analyses) - len(filtered)} 条)"
    )

    # Step 2: 按 URL 去重
    seen_urls: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in filtered:
        url = item.get("source_url", "")
        if url not in seen_urls:
            seen_urls.add(url)
            deduped.append(item)
    logger.info(
        f"[organize_node] 去重: {len(filtered)} -> {len(deduped)} "
        f"(移除 {len(filtered) - len(deduped)} 条)"
    )

    # Step 3: 如果是重试且有反馈，用 LLM 修正
    articles: list[dict[str, Any]] = []
    if iteration > 0 and feedback:
        logger.info("[organize_node] 检测到审核反馈，调用 LLM 修正")
        for item in deduped:
            try:
                prompt = REVISE_SYSTEM_PROMPT.format(
                    article=json.dumps(item, ensure_ascii=False, indent=2),
                    feedback=feedback,
                )
                revised, usage = chat_json(prompt, system=None, node_name="organize")
                accumulate_usage(cost_tracker, usage)

                # 保留原始元数据
                revised["source_url"] = item.get("source_url", "")
                revised["source_type"] = item.get("source_type", "")
                articles.append(revised)

            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"[organize_node] 修正失败，保留原文: {e}")
                articles.append(item)
    else:
        articles = deduped

    # 构建最终 articles 结构
    result_articles: list[dict[str, Any]] = []
    for item in articles:
        result_articles.append(
            {
                "id": str(uuid.uuid4()),
                "title": item.get("title", ""),
                "source_url": item.get("source_url", ""),
                "source_type": item.get("source_type", "github"),
                "summary": item.get("summary", ""),
                "tags": item.get("tags", []),
                "tech_direction": item.get("tech_direction", ""),
                "quality_level": _score_to_level(item.get("quality_score", 0)),
                "use_case": item.get("use_case", ""),
                "status": "analyzed",
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    # 写盘前对每条 article 做 PII 掩码（防手机号/邮箱/身份证泄露）
    masked_articles = []
    total_pii = 0
    for art in result_articles:
        for field in ("summary", "title", "use_case"):
            if field in art and isinstance(art[field], str):
                filtered, detections = filter_output(art[field], mask=True)
                art[field] = filtered
                total_pii += len(detections)
                if detections:
                    logger.warning(f"[Security] {art.get('id', '?')} {field} 掩码 PII：{detections}")
        masked_articles.append(art)

    if total_pii > 0:
        logger.warning(f"[Security] organize 阶段共掩码 {total_pii} 处 PII")

    logger.info(f"[organize_node] 整理完成，最终 {len(masked_articles)} 条")
    return {"articles": masked_articles}


def _score_to_level(score: float) -> str:
    """将数值评分转换为质量等级

    Args:
        score: 0-1 的评分

    Returns:
        A/B/C 质量等级
    """
    if score >= 0.8:
        return "A"
    elif score >= 0.6:
        return "B"
    else:
        return "C"


# ============================================================
# 4. review_node: LLM 五维度评分审核
# ============================================================

REVIEW_SYSTEM_PROMPT = """你是一个严格的内容质量审核员。
请对以下知识分析结果进行五维度评分审核。

评分维度（每项 1-10 分）：
1. summary_quality: 摘要质量 - 是否准确、完整、易读
2. technical_depth: 技术深度 - 是否深入分析技术栈和实现细节
3. relevance: 相关性 - 是否与 AI/LLM/Agent 领域高度相关
4. originality: 原创性 - 项目本身是否有创新性或独特价值
5. formatting: 格式规范 - 结构是否清晰、标签是否准确

输出严格 JSON 格式：
{
    "passed": true,
    "feedback": "具体改进建议（不通过时必须填写）",
    "scores": {
        "summary_quality": 8,
        "technical_depth": 7,
        "relevance": 9,
        "originality": 6,
        "formatting": 8
    }
}

注意：passed 字段由系统根据加权总分自动判定，请设为 true。
只输出 JSON，不要有其他内容。"""

REVIEW_WEIGHTS = {
    "summary_quality": 0.25,
    "technical_depth": 0.25,
    "relevance": 0.20,
    "originality": 0.15,
    "formatting": 0.15,
}

REVIEW_PASS_THRESHOLD = 7.0
REVIEW_SAMPLE_SIZE = 5


def review_node(state: KBState) -> dict:
    """LLM 五维度评分审核

    评分维度：摘要质量(25%) / 技术深度(25%) / 相关性(20%) / 原创性(15%) / 格式规范(15%)
    加权总分 >= 7.0 为通过。iteration >= 2 时强制通过，避免无限循环。

    审核对象是 analyses（不是 articles，articles 在 organize 之后才存在）。

    Args:
        state: 当前工作流状态，需要 analyses、iteration 字段

    Returns:
        {
            "review_passed": bool,
            "review_feedback": str,
            "iteration": int,
            "cost_tracker": dict,
        } 部分状态更新
    """
    iteration = state.get("iteration", 0)
    analyses = state.get("analyses", [])
    cost_tracker = state.get("cost_tracker", {})

    plan = state.get("plan") or {}
    max_iterations = int(plan.get("max_iterations", 3))

    logger.info(f"[review_node] 开始审核 (iteration={iteration})")

    # iteration >= max_iterations 强制通过
    if iteration >= max_iterations:
        logger.warning("[review_node] 达到最大迭代次数，强制通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    # 无内容时直接通过
    if not analyses:
        logger.info("[review_node] 无条目需要审核，直接通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    # 取前 5 条作为样本（控 token 消耗）
    sample = analyses[:REVIEW_SAMPLE_SIZE]
    analyses_text = json.dumps(sample, ensure_ascii=False, indent=2)

    try:
        result, usage = chat_json(
            f"请审核以下知识分析结果：\n\n{analyses_text}",
            REVIEW_SYSTEM_PROMPT,
            temperature=0.1,
            node_name="review",
        )
        accumulate_usage(cost_tracker, usage)

        # 从 LLM 结果提取各维度分数
        scores = result.get("scores", {})
        feedback = result.get("feedback", "")

        # 用代码重算加权总分（不信任模型算术）
        weighted_sum = 0.0
        for dim, weight in REVIEW_WEIGHTS.items():
            dim_score = scores.get(dim, 5)  # 缺省值 5（中位数）
            dim_score = max(1, min(10, dim_score))  # 钳位到 1-10
            weighted_sum += dim_score * weight

        passed = weighted_sum >= REVIEW_PASS_THRESHOLD

        logger.info(
            f"[review_node] 审核结果: passed={passed}, "
            f"weighted_score={weighted_sum:.2f}, "
            f"scores={scores}"
        )

        if not passed:
            logger.info(f"[review_node] 反馈: {feedback[:100]}...")

        return {
            "review_passed": passed,
            "review_feedback": feedback if not passed else "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"[review_node] 审核异常: {e}，视为通过")
        return {
            "review_passed": True,
            "review_feedback": "",
            "iteration": iteration + 1,
            "cost_tracker": cost_tracker,
        }


# ============================================================
# 5. save_node: 写入 JSON 文件并更新索引
# ============================================================

ARTICLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge", "articles")
INDEX_FILE = os.path.join(ARTICLES_DIR, "index.json")


def save_node(state: KBState) -> dict:
    """将 articles 写入 knowledge/articles/ 目录的 JSON 文件

    每个 article 写入独立 JSON 文件（id.json），
    同时更新 index.json 索引文件。

    Args:
        state: 当前工作流状态，需要 articles 字段

    Returns:
        {"status": "published"} 部分状态更新
    """
    articles = state["articles"]
    logger.info(f"[save_node] 开始保存 {len(articles)} 条知识条目")

    # 确保目录存在
    os.makedirs(ARTICLES_DIR, exist_ok=True)

    # 加载现有索引
    index: list[dict[str, Any]] = []
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                index = json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning("[save_node] 索引文件损坏，将重建")

    # 构建已有 ID 集合（用于去重）
    existing_ids = {item["id"] for item in index}

    saved_count = 0
    for article in articles:
        article_id = article.get("id", str(uuid.uuid4()))
        article["id"] = article_id
        article["status"] = "published"

        # 写入独立文件
        filepath = os.path.join(ARTICLES_DIR, f"{article_id}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(article, f, ensure_ascii=False, indent=2)

            # 更新索引（去重）
            if article_id not in existing_ids:
                index.append(
                    {
                        "id": article_id,
                        "title": article.get("title", ""),
                        "source_url": article.get("source_url", ""),
                        "quality_level": article.get("quality_level", ""),
                        "tags": article.get("tags", []),
                        "saved_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                existing_ids.add(article_id)

            saved_count += 1

        except IOError as e:
            logger.error(f"[save_node] 保存失败 [{article_id}]: {e}")

    # 写入索引文件
    try:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        logger.info(f"[save_node] 索引已更新，共 {len(index)} 条")
    except IOError as e:
        logger.error(f"[save_node] 索引写入失败: {e}")

    logger.info(f"[save_node] 保存完成，新增 {saved_count} 条")
    return {"status": "published"}
