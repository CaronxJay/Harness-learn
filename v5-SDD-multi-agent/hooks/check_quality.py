#!/usr/bin/env python3
"""知识条目质量评分脚本

用于对知识条目 JSON 文件进行 5 维度质量评分。

使用方法：
    python3 hooks/check_quality.py <json_file> [json_file2 ...]
    python3 hooks/check_quality.py knowledge/articles/*.json

评分维度（满分 100 分）：
    - 摘要质量 (25 分)：>= 50 字满分，>= 20 字基本分，含技术关键词有奖励
    - 技术深度 (25 分)：基于文章 score 字段（1-10 映射到 0-25）
    - 格式规范 (20 分)：id、title、source_url、status、时间戳五项各 4 分
    - 标签精度 (15 分)：1-3 个合法标签最佳，有标准标签列表校验
    - 空洞词检测 (15 分)：不含空洞词

等级标准：
    - A >= 80
    - B >= 60
    - C < 60

退出码：
    - 0: 所有文件都是 A/B 级
    - 1: 存在 C 级文件

编码规范：
    - 遵循 PEP 8
    - 使用 pathlib 和 dataclass
    - 不依赖第三方库
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


# 标准标签列表
VALID_TAGS: set[str] = {
    "llm", "agent", "rag", "multimodal", "code-gen", "fine-tuning",
    "inference", "training", "dataset", "tool", "framework", "application"
}

# 技术关键词（用于摘要质量评估）
TECH_KEYWORDS: set[str] = {
    "llm", "ai", "agent", "rag", "transformer", "diffusion", "neural",
    "deep-learning", "machine-learning", "nlp", "computer-vision",
    "gpt", "claude", "gemini", "llama", "openai", "anthropic",
    "langchain", "llamaindex", "huggingface", "pytorch", "tensorflow"
}

# 空洞词黑名单（中文）
BUZZWORDS_CN: set[str] = {
    "赋能", "抓手", "闭环", "打通", "全链路", "底层逻辑", "颗粒度",
    "对齐", "拉通", "沉淀", "强大的", "革命性的"
}

# 空洞词黑名单（英文）
BUZZWORDS_EN: set[str] = {
    "groundbreaking", "revolutionary", "game-changing", "cutting-edge",
    "state-of-the-art", "next-generation", "world-class", "best-in-class",
    "synergy", "leverage", "paradigm-shift", "disruptive"
}

# 合并空洞词黑名单
BUZZWORDS: set[str] = BUZZWORDS_CN | BUZZWORDS_EN


@dataclass
class DimensionScore:
    """维度评分"""
    name: str
    max_score: int
    score: int
    details: str = ""


@dataclass
class QualityReport:
    """质量报告"""
    file_path: Path
    dimensions: list[DimensionScore] = field(default_factory=list)
    total_score: int = 0
    grade: str = ""

    def calculate_total(self) -> None:
        """计算总分和等级"""
        self.total_score = sum(d.score for d in self.dimensions)
        if self.total_score >= 80:
            self.grade = "A"
        elif self.total_score >= 60:
            self.grade = "B"
        else:
            self.grade = "C"


def check_summary_quality(entry: dict) -> DimensionScore:
    """检查摘要质量（25 分）

    规则：
    - >= 50 字：满分 25 分
    - >= 20 字：基本分 15 分
    - < 20 字：0 分
    - 含技术关键词：+5 分（不超过 25 分）
    """
    summary = entry.get("summary", "")
    score = 0
    details = []

    # 基础分
    if len(summary) >= 50:
        score = 20
        details.append(f"长度 {len(summary)} 字 (>=50)")
    elif len(summary) >= 20:
        score = 10
        details.append(f"长度 {len(summary)} 字 (>=20)")
    else:
        score = 0
        details.append(f"长度 {len(summary)} 字 (<20)")

    # 技术关键词奖励
    summary_lower = summary.lower()
    found_keywords = [kw for kw in TECH_KEYWORDS if kw in summary_lower]
    if found_keywords:
        bonus = min(5, 25 - score)
        score += bonus
        details.append(f"含技术关键词: {', '.join(found_keywords[:3])}")

    score = min(25, score)

    return DimensionScore(
        name="摘要质量",
        max_score=25,
        score=score,
        details="; ".join(details)
    )


def check_tech_depth(entry: dict) -> DimensionScore:
    """检查技术深度（25 分）

    规则：
    - 基于文章 score 字段（1-10 映射到 0-25）
    - 无 score 字段：默认 10 分
    """
    score_value = entry.get("score")

    if score_value is None:
        return DimensionScore(
            name="技术深度",
            max_score=25,
            score=10,
            details="无 score 字段，默认 10 分"
        )

    if not isinstance(score_value, (int, float)):
        return DimensionScore(
            name="技术深度",
            max_score=25,
            score=0,
            details=f"score 类型错误: {type(score_value).__name__}"
        )

    # 1-10 映射到 0-25
    normalized_score = max(0, min(10, score_value))
    mapped_score = int(normalized_score * 2.5)

    return DimensionScore(
        name="技术深度",
        max_score=25,
        score=mapped_score,
        details=f"score={score_value} -> {mapped_score} 分"
    )


def check_format_compliance(entry: dict) -> DimensionScore:
    """检查格式规范（20 分）

    规则：
    - id、title、source_url、status、时间戳五项各 4 分
    """
    checks = {
        "id": 4,
        "title": 4,
        "source_url": 4,
        "status": 4,
        "collected_at": 4,
    }

    score = 0
    details = []

    for field_name, field_score in checks.items():
        if field_name in entry and entry[field_name]:
            score += field_score
            details.append(f"{field_name} ✓")
        else:
            details.append(f"{field_name} ✗")

    return DimensionScore(
        name="格式规范",
        max_score=20,
        score=score,
        details="; ".join(details)
    )


def check_tag_precision(entry: dict) -> DimensionScore:
    """检查标签精度（15 分）

    规则：
    - 1-3 个合法标签：满分 15 分
    - 4-5 个合法标签：10 分
    - > 5 个合法标签：5 分
    - 0 个标签：0 分
    - 非法标签：每个扣 2 分
    """
    tags = entry.get("tags", [])

    if not isinstance(tags, list):
        return DimensionScore(
            name="标签精度",
            max_score=15,
            score=0,
            details="tags 不是数组"
        )

    if not tags:
        return DimensionScore(
            name="标签精度",
            max_score=15,
            score=0,
            details="无标签"
        )

    # 检查合法标签
    valid_tags = [tag for tag in tags if tag in VALID_TAGS]
    invalid_tags = [tag for tag in tags if tag not in VALID_TAGS]

    # 计算分数
    if len(valid_tags) <= 3:
        score = 15
    elif len(valid_tags) <= 5:
        score = 10
    else:
        score = 5

    # 非法标签扣分
    penalty = len(invalid_tags) * 2
    score = max(0, score - penalty)

    details = []
    details.append(f"合法标签 {len(valid_tags)} 个")
    if invalid_tags:
        details.append(f"非法标签 {len(invalid_tags)} 个: {', '.join(invalid_tags[:3])}")

    return DimensionScore(
        name="标签精度",
        max_score=15,
        score=score,
        details="; ".join(details)
    )


def check_buzzwords(entry: dict) -> DimensionScore:
    """检查空洞词检测（15 分）

    规则：
    - 不含空洞词：满分 15 分
    - 每个空洞词扣 3 分
    """
    summary = entry.get("summary", "")
    title = entry.get("title", "")
    text = f"{title} {summary}".lower()

    found_buzzwords = [bw for bw in BUZZWORDS if bw in text]

    if not found_buzzwords:
        return DimensionScore(
            name="空洞词检测",
            max_score=15,
            score=15,
            details="未发现空洞词"
        )

    # 每个空洞词扣 3 分
    penalty = len(found_buzzwords) * 3
    score = max(0, 15 - penalty)

    return DimensionScore(
        name="空洞词检测",
        max_score=15,
        score=score,
        details=f"发现 {len(found_buzzwords)} 个空洞词: {', '.join(found_buzzwords[:5])}"
    )


def check_entry_quality(entry: dict, file_path: Path) -> QualityReport:
    """检查单个条目的质量

    Returns:
        质量报告
    """
    report = QualityReport(file_path=file_path)

    # 执行 5 个维度的检查
    report.dimensions.append(check_summary_quality(entry))
    report.dimensions.append(check_tech_depth(entry))
    report.dimensions.append(check_format_compliance(entry))
    report.dimensions.append(check_tag_precision(entry))
    report.dimensions.append(check_buzzwords(entry))

    # 计算总分和等级
    report.calculate_total()

    return report


def print_progress_bar(score: int, max_score: int = 100, width: int = 20) -> str:
    """生成进度条"""
    filled = int(width * score / max_score)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {score}/{max_score}"


def print_report(report: QualityReport) -> None:
    """打印质量报告"""
    print(f"\n文件: {report.file_path}")
    print(f"等级: {report.grade} ({report.total_score}/100)")
    print(f"总分: {print_progress_bar(report.total_score)}")
    print("-" * 60)

    for dim in report.dimensions:
        bar = print_progress_bar(dim.score, dim.max_score, 15)
        print(f"  {dim.name:8s} {bar}  {dim.details}")


def validate_file(file_path: Path) -> list[QualityReport]:
    """校验单个文件

    Returns:
        质量报告列表
    """
    if not file_path.exists():
        print(f"错误: 文件不存在: {file_path}")
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误: JSON 解析失败: {file_path}: {e}")
        return []

    reports = []

    if isinstance(data, dict):
        report = check_entry_quality(data, file_path)
        reports.append(report)
    elif isinstance(data, list):
        for i, entry in enumerate(data):
            if isinstance(entry, dict):
                report = check_entry_quality(entry, file_path)
                reports.append(report)

    return reports


def main() -> int:
    """主函数

    Returns:
        0: 所有文件都是 A/B 级
        1: 存在 C 级文件
    """
    # 检查参数
    if len(sys.argv) < 2:
        print("用法: python3 hooks/check_quality.py <json_file> [json_file2 ...]")
        print("示例: python3 hooks/check_quality.py knowledge/articles/*.json")
        return 1

    file_paths: list[Path] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.is_file():
            file_paths.append(path)
        elif "*" in arg or "?" in arg:
            # 处理通配符
            parent = Path(".")
            expanded = list(parent.glob(arg))
            if expanded:
                file_paths.extend(expanded)
            else:
                print(f"警告: 未找到匹配的文件: {arg}")
        else:
            print(f"警告: 文件不存在: {arg}")

    if not file_paths:
        print("错误: 没有找到要检查的文件")
        return 1

    # 检查所有文件
    all_reports: list[QualityReport] = []
    file_count = len(file_paths)

    for file_path in sorted(file_paths):
        reports = validate_file(file_path)
        all_reports.extend(reports)

    # 输出结果
    if not all_reports:
        print("错误: 没有找到有效的条目")
        return 1

    # 打印每个条目的报告
    for report in all_reports:
        print_report(report)

    # 汇总统计
    grade_a = sum(1 for r in all_reports if r.grade == "A")
    grade_b = sum(1 for r in all_reports if r.grade == "B")
    grade_c = sum(1 for r in all_reports if r.grade == "C")

    print("\n" + "=" * 60)
    print(f"汇总: {len(all_reports)} 个条目")
    print(f"  A 级: {grade_a} 个")
    print(f"  B 级: {grade_b} 个")
    print(f"  C 级: {grade_c} 个")

    # 退出码
    if grade_c > 0:
        print(f"\n警告: 存在 {grade_c} 个 C 级条目")
        return 1
    else:
        print("\n所有条目都是 A/B 级")
        return 0


if __name__ == "__main__":
    sys.exit(main())
