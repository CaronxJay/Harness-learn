#!/usr/bin/env python3
"""Supervisor 监督模式 — Worker 生成 + Supervisor 审核 + 重做循环.

Worker 接收任务输出 JSON 分析报告，Supervisor 对输出做三维评分审核。
未通过则带反馈重做，最多 3 轮，超限强制返回并附加警告。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from typing import Any

from pipeline.model_client import Usage, chat_with_retry, create_provider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Helpers
# ---------------------------------------------------------------------------


async def chat(
    prompt: str,
    provider: str | None = None,
    system: str | None = None,
    temperature: float | None = None,
) -> tuple[str, Usage]:
    """Call LLM and return (text, usage) tuple.

    Args:
        prompt: User message content.
        provider: Provider name.
        system: Optional system prompt.
        temperature: Sampling temperature (0.0-2.0). None = provider default.
    """
    llm = create_provider(provider)
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = await chat_with_retry(llm, messages, **kwargs)
        return response.content, response.usage
    finally:
        await llm.close()


def _extract_json(text: str) -> str:
    """Robustly extract JSON substring from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if len(lines) > 1 else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


async def chat_json(
    prompt: str,
    provider: str | None = None,
    system: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Call LLM and return parsed JSON response.

    Args:
        prompt: User message content.
        provider: Provider name.
        system: Optional system prompt.
        temperature: Sampling temperature (0.0-2.0).
    """
    json_system = (
        (system or "")
        + "\nRespond with valid JSON only. No other text, no markdown fences."
    )
    text, _ = await chat(prompt, provider, json_system, temperature=temperature)
    return json.loads(_extract_json(text))


# ---------------------------------------------------------------------------
# Worker Agent
# ---------------------------------------------------------------------------

WORKER_TEMPERATURE = 0.9  # higher → more creative / diverse analysis

WORKER_SYSTEM = (
    "You are an expert analyst. Generate a structured analysis report in JSON "
    "format with exactly these fields: title (string), analysis (string, "
    "detailed), key_points (array of strings), conclusion (string)."
)

WORKER_PROMPT = 'Task: {task}\n\nGenerate the analysis report as JSON.'


async def _worker(task: str, feedback: str | None = None) -> dict[str, Any]:
    """Worker Agent: generate a structured analysis report.

    Args:
        task: The analysis task description.
        feedback: Optional feedback from previous review for revision.

    Returns:
        Parsed JSON report dict with title/analysis/key_points/conclusion.
    """
    if feedback:
        prompt = (
            f"Previous review feedback: {feedback}\n\n"
            f"Please revise the report addressing all feedback above.\n\n"
            f"{WORKER_PROMPT.format(task=task)}"
        )
    else:
        prompt = WORKER_PROMPT.format(task=task)

    logger.info("Worker generating report (feedback: %s)", "yes" if feedback else "no")
    result = await chat_json(prompt, system=WORKER_SYSTEM, temperature=WORKER_TEMPERATURE)
    return result


# ---------------------------------------------------------------------------
# Supervisor Agent
# ---------------------------------------------------------------------------

SUPERVISOR_TEMPERATURE = 0.2  # lower → more deterministic / consistent scoring

SUPERVISOR_SYSTEM = (
    "You are a strict quality reviewer. Evaluate analysis reports on three "
    "dimensions: accuracy (factual correctness, 1-10), depth (thoroughness and "
    "insight, 1-10), format (clarity and structure, 1-10).\n"
    "Return JSON with: passed (bool, true if total score >= 21), accuracy "
    "(int), depth (int), format (int), score (int, sum of three), feedback "
    "(string, constructive if not passed)."
)

SUPERVISOR_PROMPT = (
    "Task: {task}\n\n"
    "Report to review:\n"
    "---\n"
    "{report}\n"
    "---\n\n"
    "Evaluate and return the review as JSON."
)

PASS_THRESHOLD = 21  # average 7 across three 1-10 dimensions


async def _supervise(task: str, report: dict[str, Any]) -> dict[str, Any]:
    """Supervisor Agent: review the worker's output.

    Args:
        task: The original task description.
        report: The worker's parsed report dict.

    Returns:
        Review dict with passed/score/accuracy/depth/format/feedback.
    """
    prompt = SUPERVISOR_PROMPT.format(task=task, report=json.dumps(report, ensure_ascii=False, indent=2))

    logger.info("Supervisor reviewing...")
    result = await chat_json(prompt, system=SUPERVISOR_SYSTEM, temperature=SUPERVISOR_TEMPERATURE)

    # Normalize: ensure required fields exist
    result.setdefault("passed", result.get("score", 0) >= PASS_THRESHOLD)
    result.setdefault("accuracy", 0)
    result.setdefault("depth", 0)
    result.setdefault("format", 0)
    result.setdefault("feedback", "")
    if "score" not in result:
        result["score"] = result["accuracy"] + result["depth"] + result["format"]

    logger.info(
        "Review: passed=%s score=%d (a=%d d=%d f=%d)",
        result["passed"],
        result["score"],
        result["accuracy"],
        result["depth"],
        result["format"],
    )
    return result


# ---------------------------------------------------------------------------
# Supervisor Orchestrator
# ---------------------------------------------------------------------------


async def supervisor(task: str, max_retries: int = 3) -> dict[str, Any]:
    """Orchestrate the worker-supervisor loop with retries.

    The worker generates an analysis report; the supervisor reviews it.
    If the report passes (total score >= 21), it is returned immediately.
    Otherwise the worker revises with feedback, up to max_retries rounds.
    After max_retries rounds without passing, the last report is force-returned
    with a warning.

    Args:
        task: The analysis task description.
        max_retries: Maximum review rounds (default 3).

    Returns:
        Dict with keys:
            output: The final worker report (dict).
            attempts: Number of review rounds executed.
            final_score: The last supervisor score (int).
            warning: Present only if max_retries exceeded without passing.
            reviews: List of all review dicts for audit trail.
    """
    if not task or not task.strip():
        return {"error": "task cannot be empty"}

    task = task.strip()
    feedback: str | None = None
    reviews: list[dict[str, Any]] = []
    final_report: dict[str, Any] = {}

    for attempt in range(1, max_retries + 1):
        logger.info("=== Round %d/%d ===", attempt, max_retries)

        # Worker step
        report = await _worker(task, feedback)
        final_report = report

        # Supervisor step
        review = await _supervise(task, report)
        reviews.append(review)

        if review["passed"]:
            logger.info("Passed at round %d", attempt)
            return {
                "output": report,
                "attempts": attempt,
                "final_score": review["score"],
                "accuracy": review["accuracy"],
                "depth": review["depth"],
                "format": review["format"],
                "reviews": reviews,
            }

        feedback = review.get("feedback", "Please improve the report quality.")
        logger.info("Failed round %d — score=%d, will retry with feedback", attempt, review["score"])

    # Exceeded max_retries: force-return with warning
    last_review = reviews[-1] if reviews else {}
    logger.warning("Max retries (%d) exceeded, force-returning", max_retries)

    return {
        "output": final_report,
        "attempts": max_retries,
        "final_score": last_review.get("score", 0),
        "accuracy": last_review.get("accuracy", 0),
        "depth": last_review.get("depth", 0),
        "format": last_review.get("format", 0),
        "warning": (
            f"Report did not meet quality threshold after {max_retries} rounds. "
            f"Final score: {last_review.get('score', 'N/A')}/30. "
            f"Last feedback: {last_review.get('feedback', 'N/A')}"
        ),
        "reviews": reviews,
    }


# ---------------------------------------------------------------------------
# Test Entry
# ---------------------------------------------------------------------------


def _run_tests() -> None:
    """Run supervisor self-tests."""
    print("=" * 60)
    print("  patterns/supervisor.py — Supervisor 监督模式测试")
    print("=" * 60)

    api_key = os.getenv("API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("\n  未检测到 API_KEY，请设置 DEEPSEEK_API_KEY 后重试。")
        return

    print(f"  LLM 已配置 (provider: {os.getenv('LLM_PROVIDER', 'deepseek')})")
    print(f"  通过阈值: 21/30 (每维度平均 7/10)\n")

    async def _live_test() -> None:
        task = "分析 LangGraph 和 CrewAI 这两个多 Agent 框架的架构差异及适用场景"

        print(f"  ── 任务: {task}")
        print()
        try:
            result = await supervisor(task, max_retries=2)
        except Exception as exc:
            print(f"  执行失败: {exc}")
            return

        print(f"  完成轮次: {result['attempts']}")
        print(f"  最终评分: {result['final_score']}/30")
        if "warning" in result:
            print(f"  ⚠ 警告: {result['warning']}")
        print()

        output = result["output"]
        print(f"  标题: {output.get('title', 'N/A')}")
        analysis = output.get("analysis", "")
        if len(analysis) > 200:
            analysis = analysis[:200] + "..."
        print(f"  分析: {analysis}")
        print(f"  要点: {'; '.join(output.get('key_points', [])[:3])}")
        print(f"  结论: {output.get('conclusion', 'N/A')[:150]}")

        print(f"\n  ── 审核记录:")
        for i, r in enumerate(result.get("reviews", []), 1):
            print(
                f"    第{i}轮: score={r['score']} "
                f"(准确性={r['accuracy']} 深度={r['depth']} 格式={r['format']}) "
                f"→ {'✓ 通过' if r['passed'] else '✗ 重做'}"
            )
            if not r["passed"] and r.get("feedback"):
                fb = r["feedback"][:120]
                print(f"           反馈: {fb}...")

    asyncio.run(_live_test())

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        result = asyncio.run(supervisor(task))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _run_tests()
