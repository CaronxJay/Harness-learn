"""Supervisor 监督模式

Worker-Supervisor 双 Agent 协作模式：
- Worker Agent：接收任务，输出 JSON 格式的分析报告
- Supervisor Agent：对 Worker 输出进行质量审核
- 审核循环：通过(score>=7)返回 / 不通过带反馈重做 / 超过 max_retries 强制返回

使用方法：
    from patterns.supervisor import supervisor

    result = supervisor("分析 LangChain 框架的优缺点")
    print(result["output"])       # 分析报告
    print(result["attempts"])     # 尝试次数
    print(result["final_score"])  # 最终评分
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


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
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


# ============================================================
# Worker Agent
# ============================================================

WORKER_SYSTEM_PROMPT = """你是一个专业的技术分析助手。请根据用户任务输出 JSON 格式的分析报告。

输出格式要求：
{
    "title": "报告标题",
    "summary": "核心摘要（100-200字）",
    "key_points": ["要点1", "要点2", "要点3"],
    "analysis": "详细分析（300-500字）",
    "conclusion": "结论"
}

只输出 JSON，不要有其他内容。"""


def worker_agent(task: str, feedback: Optional[str] = None) -> str:
    """Worker Agent：执行分析任务

    Args:
        task: 分析任务描述
        feedback: Supervisor 的反馈（重做时提供）

    Returns:
        JSON 格式的分析报告字符串
    """
    prompt = task
    if feedback:
        prompt = f"""上一轮分析被 Supervisor 退回，反馈如下：

{feedback}

请根据反馈重新分析以下任务：

{task}"""

    logger.info(f"Worker Agent 执行任务{'（含反馈重做）' if feedback else ''}")
    text, _ = chat(prompt, WORKER_SYSTEM_PROMPT)
    return text.strip()


# ============================================================
# Supervisor Agent
# ============================================================

SUPERVISOR_SYSTEM_PROMPT = """你是一个严格的质量审核员。请对 Worker 输出的分析报告进行质量评估。

评分维度（每项 1-10 分）：
- 准确性：内容是否准确、无明显错误
- 深度：分析是否深入、有洞察力
- 格式：是否为有效 JSON、结构是否清晰

输出格式要求（严格 JSON）：
{
    "passed": true/false,
    "score": 总分（三项平均，1-10），
    "feedback": "具体改进建议（不通过时必须填写）"
}

通过标准：score >= 7
只输出 JSON，不要有其他内容。"""


def supervisor_agent(report: str) -> dict:
    """Supervisor Agent：审核分析报告

    Args:
        report: Worker 输出的 JSON 报告

    Returns:
        审核结果 {"passed": bool, "score": int, "feedback": str}
    """
    prompt = f"""请审核以下分析报告：

{report}"""

    logger.info("Supervisor Agent 审核报告")
    result = chat_json(prompt, SUPERVISOR_SYSTEM_PROMPT)
    return result


# ============================================================
# Supervisor 监督循环
# ============================================================

def supervisor(task: str, max_retries: int = 3) -> dict:
    """Supervisor 监督模式入口

    流程：
    1. Worker 执行任务，输出分析报告
    2. Supervisor 审核报告
    3. 通过(score>=7) → 返回结果
    4. 不通过 → 带反馈重做（最多 max_retries 轮）
    5. 超过 max_retries → 强制返回 + 警告

    Args:
        task: 分析任务描述
        max_retries: 最大重试次数，默认 3

    Returns:
        {
            "output": 分析报告内容,
            "attempts": 尝试次数,
            "final_score": 最终评分,
            "warning": 警告信息（可选）
        }
    """
    logger.info(f"Supervisor 启动，任务: {task[:50]}...，最大重试: {max_retries}")

    feedback = None
    last_report = None
    last_review = None

    for attempt in range(1, max_retries + 1):
        logger.info(f"=== 第 {attempt}/{max_retries} 轮 ===")

        # Worker 执行任务
        report_text = worker_agent(task, feedback)

        # 尝试解析 Worker 输出
        try:
            report_json = json.loads(report_text)
            last_report = report_json
        except json.JSONDecodeError:
            logger.warning(f"Worker 输出非有效 JSON，尝试修复")
            # 尝试提取 JSON
            try:
                if "```" in report_text:
                    lines = report_text.split("\n")
                    json_str = "\n".join(
                        lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                    )
                    report_json = json.loads(json_str)
                    last_report = report_json
                else:
                    last_report = {"raw_output": report_text}
            except json.JSONDecodeError:
                last_report = {"raw_output": report_text}

        # Supervisor 审核
        try:
            review = supervisor_agent(report_text)
            last_review = review
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Supervisor 审核失败: {e}")
            # 审核失败时视为通过，避免无限循环
            return {
                "output": last_report,
                "attempts": attempt,
                "final_score": 0,
                "warning": f"Supervisor 审核异常: {e}",
            }

        score = review.get("score", 0)
        passed = review.get("passed", False)
        feedback = review.get("feedback", "")

        logger.info(f"审核结果: score={score}, passed={passed}")

        # 通过检查
        if passed and score >= 7:
            logger.info(f"审核通过（第 {attempt} 轮），score={score}")
            return {
                "output": last_report,
                "attempts": attempt,
                "final_score": score,
            }

        # 未通过，记录反馈用于下一轮
        logger.info(f"审核未通过，反馈: {feedback[:100]}...")

    # 超过最大重试次数，强制返回
    logger.warning(f"超过最大重试次数 ({max_retries})，强制返回")
    final_score = last_review.get("score", 0) if last_review else 0

    return {
        "output": last_report,
        "attempts": max_retries,
        "final_score": final_score,
        "warning": f"已达到最大重试次数 ({max_retries})，结果可能不符合质量要求",
    }


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("=" * 60)
    logger.info("Supervisor 监督模式测试")
    logger.info("=" * 60)

    # 测试任务
    test_task = "分析 Python 异步编程（asyncio）的优缺点，以及适用场景"

    logger.info(f"\n任务: {test_task}")
    logger.info("-" * 40)

    result = supervisor(test_task, max_retries=3)

    logger.info("\n" + "=" * 40)
    logger.info("最终结果:")
    logger.info(f"  尝试次数: {result['attempts']}")
    logger.info(f"  最终评分: {result['final_score']}")
    if "warning" in result:
        logger.warning(f"  警告: {result['warning']}")

    logger.info("\n分析报告:")
    logger.info(json.dumps(result["output"], ensure_ascii=False, indent=2))
