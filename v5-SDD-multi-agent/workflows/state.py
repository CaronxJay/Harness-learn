"""LangGraph 工作流共享状态定义

KBState 是知识库工作流的核心状态结构，所有 Agent 节点通过读写此状态进行通信。

遵循"报告式通信"原则：
- 字段存储结构化摘要，不是原始数据
- 每个节点输出精炼的分析结果，而非冗长的原始文本
- 状态流转清晰，便于调试和追踪

使用方法：
    from workflows.state import KBState

    state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {},
    }
"""

from typing import TypedDict


class KBState(TypedDict):
    """知识库工作流共享状态

    所有 Agent 节点通过此 TypedDict 进行数据交换，
    状态在 LangGraph 图节点间流转。
    """

    plan: dict
    """Planner 输出策略

    Planner Agent 根据任务需求生成的执行计划，
    包含数据源选择、分析策略等决策信息。
    """

    sources: list[dict]
    """采集到的原始数据列表

    每个 dict 结构：
    {
        "url": "来源链接",
        "title": "标题",
        "content": "摘要或关键内容",
        "source_type": "github | hackernews | rss",
        "collected_at": "采集时间 ISO 格式"
    }
    """

    analyses: list[dict]
    """LLM 分析后的结构化结果列表

    每个 dict 结构：
    {
        "title": "分析标题",
        "summary": "AI 生成的中文摘要",
        "tags": ["llm", "agent", "rag"],
        "tech_direction": "llm | agent | rag | infra | tool",
        "quality_level": "A | B | C",
        "use_case": "适用场景描述",
        "source_url": "原始来源链接"
    }
    """

    articles: list[dict]
    """格式化、去重后的知识条目列表

    每个 dict 结构：
    {
        "id": "UUID",
        "title": "条目标题",
        "source_url": "来源链接",
        "source_type": "github | hackernews",
        "summary": "中文摘要",
        "tags": ["llm", "agent"],
        "tech_direction": "llm",
        "quality_level": "A",
        "use_case": "适用场景",
        "status": "raw | analyzed | published",
        "collected_at": "采集时间 ISO 格式"
    }
    """

    review_feedback: str
    """审核反馈意见

    Supervisor Agent 审核后的具体改进建议，
    用于指导下一轮分析优化。通过时为空字符串。
    """

    review_passed: bool
    """审核是否通过

    True: 质量达标，可进入存档阶段
    False: 需要重新分析
    """

    iteration: int
    """当前审核循环次数

    范围: 0-3
    达到 3 次仍未通过时，强制进入存档并附加警告。
    """

    cost_tracker: dict
    """Token 用量追踪

    结构：
    {
        "total_tokens": int,
        "prompt_tokens": int,
        "completion_tokens": int,
        "estimated_cost": float  # 估算成本（元）
    }
    """

    needs_human_review: bool
    """是否需要人工介入

    True: 审核循环超过上限，问题条目已写入 pending_review/
    False: 正常流程
    """
