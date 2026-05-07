"""多 Agent 预算守卫模块。

提供 LLM 调用成本追踪、预算预警和超限保护能力。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

TZ_UTC8 = timezone(timedelta(hours=8))
MILLION = 1_000_000

logger = logging.getLogger(__name__)


@dataclass
class CostRecord:
    """记录单次 LLM 调用的用量与成本。

    Attributes:
        timestamp: 调用时间（UTC+8）。
        node_name: 发起调用的 Agent / 节点名称。
        prompt_tokens: 输入 token 数。
        completion_tokens: 输出 token 数。
        cost_yuan: 本次调用费用（元）。
        model: 模型名称。
    """

    timestamp: datetime
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: float
    model: str


class BudgetExceededError(Exception):
    """预算超限异常。

    Attributes:
        total_cost: 当前累计成本。
        budget: 预算上限。
        message: 错误描述。
    """

    def __init__(
        self,
        total_cost: float,
        budget: float,
        message: str = "",
    ) -> None:
        self.total_cost = total_cost
        self.budget = budget
        full_message = (
            message
            or f"Budget exceeded: total cost ¥{total_cost:.4f} > budget ¥{budget:.4f}"
        )
        super().__init__(full_message)


class CostGuard:
    """多 Agent 预算守卫，提供成本追踪、预警和超限保护。

    支持三重保护机制：
        1. record() — 记录每次 LLM 调用的用量并计算成本。
        2. check() — 按预警阈值检查预算状态（warning / exceed）。
        3. get_report() / save_report() — 生成并持久化成本报告。

    Attributes:
        budget_yuan: 总预算（元）。
        alert_threshold: 预警阈值（预算使用比例，0.0-1.0）。
        input_price_per_million: 百万输入 token 单价（元）。
        output_price_per_million: 百万输出 token 单价（元）。
        records: 已记录的所有调用明细。
    """

    def __init__(
        self,
        budget_yuan: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
    ) -> None:
        """初始化预算守卫。

        Args:
            budget_yuan: 总预算（元）。
            alert_threshold: 预警阈值，预算使用比例达到此值时触发 warning。
            input_price_per_million: 百万输入 token 单价（元）。
            output_price_per_million: 百万输出 token 单价（元）。
        """
        self.budget_yuan = budget_yuan
        self.alert_threshold = alert_threshold
        self.input_price_per_million = input_price_per_million
        self.output_price_per_million = output_price_per_million
        self.records: list[CostRecord] = []

    # ------------------------------------------------------------------
    # 聚合属性
    # ------------------------------------------------------------------

    @property
    def total_cost_yuan(self) -> float:
        """累计成本（元）。"""
        return sum(r.cost_yuan for r in self.records)

    @property
    def total_prompt_tokens(self) -> int:
        """累计输入 token 数。"""
        return sum(r.prompt_tokens for r in self.records)

    @property
    def total_completion_tokens(self) -> int:
        """累计输出 token 数。"""
        return sum(r.completion_tokens for r in self.records)

    @property
    def usage_ratio(self) -> float:
        """当前预算使用比例 (0.0-∞)。"""
        return self.total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 0.0

    # ------------------------------------------------------------------
    # 核心方法
    # ------------------------------------------------------------------

    def record(
        self,
        node_name: str,
        usage: dict[str, int],
        model: str = "",
    ) -> None:
        """记录一次 LLM 调用。

        Args:
            node_name: 发起调用的 Agent / 节点名称。
            usage: token 用量字典，格式 {"prompt_tokens": int, "completion_tokens": int}。
            model: 模型名称（可选）。

        Raises:
            KeyError: usage 缺少必要字段时抛出。
        """
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]

        cost = (
            prompt_tokens / MILLION * self.input_price_per_million
            + completion_tokens / MILLION * self.output_price_per_million
        )
        cost = round(cost, 6)

        record = CostRecord(
            timestamp=datetime.now(TZ_UTC8),
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost,
            model=model or "",
        )
        self.records.append(record)

        logger.info(
            "Recorded call on [%s]: %d prompt + %d completion = ¥%.6f (model=%s)",
            node_name,
            prompt_tokens,
            completion_tokens,
            cost,
            model or "unknown",
        )

    def check(self) -> dict[str, Any]:
        """检查当前预算状态。

        Returns:
            状态字典，包含:
                status: "ok" | "warning"
                total_cost: 当前累计成本。
                budget: 预算上限。
                usage_ratio: 预算使用比例。
                message: 状态描述。

        Raises:
            BudgetExceededError: 累计成本超过预算上限时抛出。
        """
        total = self.total_cost_yuan
        ratio = total / self.budget_yuan if self.budget_yuan > 0 else 0.0

        if total > self.budget_yuan:
            logger.error(
                "Budget exceeded: ¥%.4f / ¥%.4f (%.1f%%)",
                total,
                self.budget_yuan,
                ratio * 100,
            )
            raise BudgetExceededError(
                total_cost=total,
                budget=self.budget_yuan,
            )

        if ratio >= self.alert_threshold:
            logger.warning(
                "Budget warning: ¥%.4f / ¥%.4f (%.1f%%)",
                total,
                self.budget_yuan,
                ratio * 100,
            )
            return {
                "status": "warning",
                "total_cost": total,
                "budget": self.budget_yuan,
                "usage_ratio": ratio,
                "message": (
                    f"预算使用已达 {ratio:.1%}，"
                    f"当前 ¥{total:.4f} / ¥{self.budget_yuan:.4f}"
                ),
            }

        return {
            "status": "ok",
            "total_cost": total,
            "budget": self.budget_yuan,
            "usage_ratio": ratio,
            "message": f"预算使用正常，当前 ¥{total:.4f} / ¥{self.budget_yuan:.4f}",
        }

    def get_report(self) -> dict[str, Any]:
        """生成按节点分组的成本报告。

        Returns:
            报告字典，包含:
                summary: 汇总统计（总调用次数、总 token、总成本等）。
                by_node: 按 node_name 分组统计。
                records: 原始记录列表。
        """
        # 按节点分组
        by_node: dict[str, dict[str, Any]] = {}
        for r in self.records:
            if r.node_name not in by_node:
                by_node[r.node_name] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost_yuan": 0.0,
                }
            node = by_node[r.node_name]
            node["calls"] += 1
            node["prompt_tokens"] += r.prompt_tokens
            node["completion_tokens"] += r.completion_tokens
            node["cost_yuan"] = round(node["cost_yuan"] + r.cost_yuan, 6)

        return {
            "summary": {
                "total_calls": len(self.records),
                "total_prompt_tokens": self.total_prompt_tokens,
                "total_completion_tokens": self.total_completion_tokens,
                "total_cost_yuan": round(self.total_cost_yuan, 6),
                "budget_yuan": self.budget_yuan,
                "usage_ratio": round(self.usage_ratio, 6),
            },
            "by_node": by_node,
            "records": [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "node_name": r.node_name,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "cost_yuan": r.cost_yuan,
                    "model": r.model,
                }
                for r in self.records
            ],
        }

    def save_report(self, path: Optional[str] = None) -> str:
        """将成本报告保存为 JSON 文件。

        Args:
            path: 目标文件路径。未指定时默认保存到
                knowledge/reports/cost_report_{timestamp}.json。

        Returns:
            实际写入的文件路径。
        """
        if path is None:
            ts = datetime.now(TZ_UTC8).strftime("%Y%m%d_%H%M%S")
            output_dir = Path("knowledge") / "reports"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = str(output_dir / f"cost_report_{ts}.json")

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        report = self.get_report()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info("Cost report saved to %s", path)
        return path


# ======================================================================
# 自测代码
# ======================================================================
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    errors: list[str] = []

    # ---- 用例 1：成本追踪正确性 ----
    print("=" * 60)
    print("Test 1: Cost tracking accuracy")
    print("=" * 60)

    guard = CostGuard(
        budget_yuan=1.0,
        alert_threshold=0.8,
        input_price_per_million=1.0,
        output_price_per_million=2.0,
    )
    guard.record("collector", {"prompt_tokens": 200_000, "completion_tokens": 5_000})
    guard.record("analyzer", {"prompt_tokens": 100_000, "completion_tokens": 80_000})

    # 手动计算期望值
    # record 1: 200000/1e6*1.0 + 5000/1e6*2.0 = 0.2 + 0.01 = 0.21
    # record 2: 100000/1e6*1.0 + 80000/1e6*2.0 = 0.1 + 0.16 = 0.26
    # total cost = 0.47, total prompt = 300000

    assert guard.total_prompt_tokens == 300_000, (
        f"Expected 300000 prompt tokens, got {guard.total_prompt_tokens}"
    )
    assert guard.total_cost_yuan == 0.47, (
        f"Expected 0.47 cost, got {guard.total_cost_yuan}"
    )
    print(f"  prompt_tokens = {guard.total_prompt_tokens}")
    print(f"  completion_tokens = {guard.total_completion_tokens}")
    print(f"  total_cost = ¥{guard.total_cost_yuan:.4f}")
    print("  PASS")

    # ---- 用例 2：预警阈值触发 ----
    print()
    print("=" * 60)
    print("Test 2: Alert threshold triggers warning")
    print("=" * 60)

    # 再加一笔让 cost 达到 0.85（超过 0.8 阈值）
    # 需要 extra cost = 0.85 - 0.47 = 0.38
    # 用 prompt 来凑: 0.38 / 1.0 * 1e6 = 380000
    guard.record("publisher", {"prompt_tokens": 380_000, "completion_tokens": 0})

    result = guard.check()
    assert result["status"] == "warning", f"Expected 'warning', got {result['status']}"
    assert result["usage_ratio"] >= 0.8, (
        f"Expected usage_ratio >= 0.8, got {result['usage_ratio']}"
    )
    print(f"  status = {result['status']}")
    print(f"  usage_ratio = {result['usage_ratio']:.2%}")
    print(f"  message = {result['message']}")
    print("  PASS")

    # ---- 用例 3：预算超限检测 ----
    print()
    print("=" * 60)
    print("Test 3: Budget exceeded raises exception")
    print("=" * 60)

    # 再加一笔让 cost 超过 1.0
    # 当前 cost = 0.47 + 0.38 = 0.85
    # 需要 > 0.15，用 prompt：0.16 / 1.0 * 1e6 = 160000
    guard.record("analyzer", {"prompt_tokens": 200_000, "completion_tokens": 0})

    try:
        guard.check()
        errors.append("BudgetExceededError was NOT raised when budget exceeded")
        print("  FAIL: Expected BudgetExceededError but none raised")
    except BudgetExceededError as e:
        print(f"  Caught BudgetExceededError: {e}")
        print(f"  total_cost = ¥{e.total_cost:.4f}, budget = ¥{e.budget:.4f}")
        print("  PASS")

    # ---- 用例 4：报告生成 ----
    print()
    print("=" * 60)
    print("Test 4: Report generation")
    print("=" * 60)

    report = guard.get_report()
    assert report["summary"]["total_calls"] == 4, (
        f"Expected 4 calls, got {report['summary']['total_calls']}"
    )
    assert "collector" in report["by_node"]
    assert "analyzer" in report["by_node"]
    assert "publisher" in report["by_node"]

    collector_stats = report["by_node"]["collector"]
    assert collector_stats["calls"] == 1
    assert collector_stats["prompt_tokens"] == 200_000
    assert collector_stats["completion_tokens"] == 5_000

    analyzer_stats = report["by_node"]["analyzer"]
    assert analyzer_stats["calls"] == 2

    print(f"  summary: {json.dumps(report['summary'], indent=2)}")
    print(f"  nodes: {list(report['by_node'].keys())}")
    print("  PASS")

    # ---- 用例 5：保存报告 ----
    print()
    print("=" * 60)
    print("Test 5: Save report to file")
    print("=" * 60)

    save_path = guard.save_report("knowledge/reports/test_cost_report.json")
    assert Path(save_path).exists(), f"Report file not found: {save_path}"
    print(f"  Report saved to {save_path}")
    print("  PASS")

    # ---- 汇总 ----
    print()
    print("=" * 60)
    if errors:
        print(f"FAILED ({len(errors)} error(s)):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("All tests PASSED")
        sys.exit(0)
