"""CostGuard — 多 Agent 预算守卫

三重保护机制：
1. 记录每次 LLM 调用的 token 用量和成本
2. 接近预算时发出预警（warning）
3. 超出预算时抛出 BudgetExceededError

使用方法：
    from tests.cost_guard import CostGuard, BudgetExceededError

    guard = CostGuard(budget_yuan=1.0)
    guard.record("analyzer", {"prompt_tokens": 100, "completion_tokens": 200})
    status = guard.check()
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """预算超限异常"""

    def __init__(self, message: str, total_cost: float, budget: float):
        super().__init__(message)
        self.total_cost = total_cost
        self.budget = budget


@dataclass
class CostRecord:
    """单次 LLM 调用记录"""

    timestamp: str
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: float
    model: str = ""


class CostGuard:
    """多 Agent 预算守卫

    Args:
        budget_yuan: 总预算（元），默认 1.0
        alert_threshold: 预警阈值（0-1），默认 0.8
        input_price_per_million: 输入 token 单价（元/百万 token），默认 1.0
        output_price_per_million: 输出 token 单价（元/百万 token），默认 2.0
    """

    def __init__(
        self,
        budget_yuan: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
    ):
        self.budget = budget_yuan
        self.alert_threshold = alert_threshold
        self.input_price = input_price_per_million / 1_000_000
        self.output_price = output_price_per_million / 1_000_000
        self.records: list[CostRecord] = []

    def record(
        self,
        node_name: str,
        usage: dict[str, int],
        model: str = "",
    ) -> None:
        """记录一次 LLM 调用的 token 用量

        Args:
            node_name: 节点名称（如 "analyzer"、"reviewer"）
            usage: token 用量，格式 {"prompt_tokens": int, "completion_tokens": int}
            model: 模型名称（可选）
        """
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))

        cost = (
            prompt_tokens * self.input_price
            + completion_tokens * self.output_price
        )

        record = CostRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost,
            model=model,
        )
        self.records.append(record)

        logger.debug(
            f"[CostGuard] {node_name}: +{cost:.6f} 元 "
            f"(in={prompt_tokens}, out={completion_tokens})"
        )

    def check(self) -> dict[str, Any]:
        """检查预算状态

        Returns:
            {"status": "ok"|"warning"|"exceeded", "total_cost": float,
             "budget": float, "usage_ratio": float, "message": str}

        Raises:
            BudgetExceededError: 当总成本超出预算时
        """
        total_cost = sum(r.cost_yuan for r in self.records)
        usage_ratio = total_cost / self.budget if self.budget > 0 else 0.0

        if usage_ratio >= 1.0:
            raise BudgetExceededError(
                message=f"预算已超限: 花费 {total_cost:.4f} 元 / 预算 {self.budget:.4f} 元",
                total_cost=total_cost,
                budget=self.budget,
            )

        if usage_ratio >= self.alert_threshold:
            return {
                "status": "warning",
                "total_cost": total_cost,
                "budget": self.budget,
                "usage_ratio": usage_ratio,
                "message": (
                    f"接近预算上限: 已用 {usage_ratio:.1%} "
                    f"({total_cost:.4f}/{self.budget:.4f} 元)"
                ),
            }

        return {
            "status": "ok",
            "total_cost": total_cost,
            "budget": self.budget,
            "usage_ratio": usage_ratio,
            "message": f"预算正常: 已用 {usage_ratio:.1%}",
        }

    def get_report(self) -> dict[str, Any]:
        """生成成本报告（按节点分组统计）

        Returns:
            包含汇总和分节点明细的报告 dict
        """
        by_node: dict[str, dict[str, Any]] = {}

        for r in self.records:
            if r.node_name not in by_node:
                by_node[r.node_name] = {
                    "call_count": 0,
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_cost_yuan": 0.0,
                }
            node = by_node[r.node_name]
            node["call_count"] += 1
            node["total_prompt_tokens"] += r.prompt_tokens
            node["total_completion_tokens"] += r.completion_tokens
            node["total_cost_yuan"] += r.cost_yuan

        total_cost = sum(r.cost_yuan for r in self.records)

        return {
            "summary": {
                "total_calls": len(self.records),
                "total_cost_yuan": total_cost,
                "budget": self.budget,
                "usage_ratio": total_cost / self.budget if self.budget > 0 else 0.0,
            },
            "by_node": by_node,
        }

    def save_report(self, path: str | Path | None = None) -> Path:
        """保存成本报告到 JSON 文件

        Args:
            path: 输出路径。默认为 cost_report_<timestamp>.json

        Returns:
            写入的文件路径
        """
        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = Path(f"cost_report_{ts}.json")
        else:
            path = Path(path)

        report = self.get_report()
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[CostGuard] 报告已保存: {path}")
        return path


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(message)s")

    print("=" * 60)
    print("CostGuard 测试")
    print("=" * 60)

    # 测试 1: 成本追踪
    print("\n[测试 1] 成本追踪正确性")
    guard = CostGuard(budget_yuan=1.0)
    guard.record("collector", {"prompt_tokens": 1000, "completion_tokens": 500})
    guard.record("analyzer", {"prompt_tokens": 2000, "completion_tokens": 1000})
    guard.record("analyzer", {"prompt_tokens": 3000, "completion_tokens": 1500})

    total_prompt = sum(r.prompt_tokens for r in guard.records)
    total_cost = sum(r.cost_yuan for r in guard.records)
    # 预期: prompt=6000, completion=3000
    # 成本: 6000*1e-6 + 3000*2e-6 = 0.006 + 0.006 = 0.012
    assert total_prompt == 6000, f"Expected 6000, got {total_prompt}"
    assert abs(total_cost - 0.012) < 1e-6, f"Expected 0.012, got {total_cost}"
    print(f"  ✓ total_prompt_tokens={total_prompt}, total_cost={total_cost:.6f}")

    # 测试 2: 预算正常
    print("\n[测试 2] 预算正常状态")
    status = guard.check()
    assert status["status"] == "ok", f"Expected ok, got {status['status']}"
    print(f"  ✓ status={status['status']}, usage_ratio={status['usage_ratio']:.2%}")

    # 测试 3: 预警阈值触发
    print("\n[测试 3] 预警阈值触发")
    guard2 = CostGuard(budget_yuan=0.01, alert_threshold=0.8)
    guard2.record("node", {"prompt_tokens": 5000, "completion_tokens": 2500})
    # 成本: 5000*1e-6 + 2500*2e-6 = 0.005 + 0.005 = 0.01
    # 但这是 100%，会直接抛异常。调小一点:
    guard2 = CostGuard(budget_yuan=0.02, alert_threshold=0.8)
    guard2.record("node", {"prompt_tokens": 10000, "completion_tokens": 5000})
    # 成本: 0.01 + 0.01 = 0.02 → 100%，还是会超。再调:
    guard2 = CostGuard(budget_yuan=0.1, alert_threshold=0.8)
    guard2.record("node", {"prompt_tokens": 50000, "completion_tokens": 20000})
    # 成本: 0.05 + 0.04 = 0.09 → 90%，触发 warning
    status = guard2.check()
    assert status["status"] == "warning", f"Expected warning, got {status['status']}"
    print(f"  ✓ status={status['status']}, usage_ratio={status['usage_ratio']:.2%}")
    print(f"    message: {status['message']}")

    # 测试 4: 预算超限检测
    print("\n[测试 4] 预算超限检测")
    guard3 = CostGuard(budget_yuan=0.001)
    guard3.record("node", {"prompt_tokens": 1000, "completion_tokens": 1000})
    # 成本: 0.001 + 0.002 = 0.003 > 0.001
    try:
        guard3.check()
        print("  ✗ 应该抛出 BudgetExceededError")
    except BudgetExceededError as e:
        print(f"  ✓ 捕获异常: {e}")
        assert e.total_cost > e.budget

    # 测试 5: 报告生成
    print("\n[测试 5] 成本报告")
    report = guard.get_report()
    print(f"  ✓ 总调用: {report['summary']['total_calls']}")
    print(f"    总成本: {report['summary']['total_cost_yuan']:.6f} 元")
    for node, stats in report["by_node"].items():
        print(
            f"    [{node}] {stats['call_count']}次, "
            f"tokens={stats['total_prompt_tokens']}+{stats['total_completion_tokens']}, "
            f"cost={stats['total_cost_yuan']:.6f}元"
        )

    print("\n" + "=" * 60)
    print("全部测试通过 ✓")
    print("=" * 60)
