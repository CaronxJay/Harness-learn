#!/usr/bin/env python3
"""知识条目 5 维度质量评分工具。

对 JSON 知识条目从摘要质量、技术深度、格式规范、标签精度、
空洞词检测五个维度进行综合评分，产出等级评定 A/B/C。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CHINESE_BUZZWORDS: frozenset[str] = frozenset({
    "赋能",
    "抓手",
    "闭环",
    "打通",
    "全链路",
    "底层逻辑",
    "颗粒度",
    "对齐",
    "拉通",
    "沉淀",
    "强大的",
    "革命性的",
})

ENGLISH_BUZZWORDS: frozenset[str] = frozenset({
    "groundbreaking",
    "revolutionary",
    "game-changing",
    "game-changer",
    "cutting-edge",
    "disruptive",
    "best-in-class",
    "world-class",
    "unprecedented",
    "paradigm-shifting",
    "industry-leading",
    "bleeding-edge",
})

VALID_TAGS: frozenset[str] = frozenset({
    "agent-framework",
    "llm",
    "rag",
    "open-source",
    "fine-tuning",
    "prompt-engineering",
    "multimodal",
    "inference",
    "benchmark",
    "tool-calling",
    "embedding",
    "vector-database",
    "nlp",
    "transformer",
    "gpt",
    "langchain",
    "deep-learning",
    "machine-learning",
    "ai",
    "safety",
    "alignment",
    "evaluation",
    "deployment",
    "tutorial",
    "research",
    "application",
    "infrastructure",
    "security",
})

TECH_KEYWORDS: frozenset[str] = frozenset({
    "agent",
    "llm",
    "rag",
    "transformer",
    "fine-tune",
    "prompt",
    "multimodal",
    "embedding",
    "inference",
    "diffusion",
    "reinforcement",
    "architecture",
    "pipeline",
    "orchestration",
    "memory",
    "planning",
    "reasoning",
    "alignment",
    "quantization",
    "distillation",
})

VALID_STATUSES: frozenset[str] = frozenset({"draft", "review", "published", "archived"})
URL_PATTERN = re.compile(r"^https?://")
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]+-\d{8}-\d{3}$")
BAR_WIDTH = 20

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class DimensionScore:
    """单个维度的评分结果。"""

    name: str
    score: float
    max_score: float
    details: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """单份知识条目的质量报告。"""

    file: str
    entry_index: int
    total_score: float
    grade: str
    dimensions: list[DimensionScore]
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def render_bar(ratio: float) -> str:
    """渲染 ASCII 进度条。

    Args:
        ratio: 得分占比，范围 0.0-1.0。

    Returns:
        可视化进度条字符串。
    """
    filled = int(ratio * BAR_WIDTH)
    empty = BAR_WIDTH - filled
    return f"[{'=' * filled}{' ' * empty}]"


def collect_files(paths: list[str]) -> list[Path]:
    """收集待评分的 JSON 文件列表，支持通配符。

    Args:
        paths: 命令行传入的路径列表。

    Returns:
        去重后的 Path 对象列表。
    """
    files: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        raw_path = Path(raw)
        if raw_path.is_absolute():
            pattern_dir = raw_path.parent
            pattern_name = raw_path.name
        elif "/" in raw or "\\" in raw:
            pattern_dir = Path(raw).parent
            pattern_name = raw_path.name
        else:
            pattern_dir = Path()
            pattern_name = raw

        for matched in sorted(pattern_dir.glob(pattern_name)):
            if matched.is_file():
                resolved = str(matched.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(matched)
    return files


def load_entries(filepath: Path) -> tuple[list[dict[str, Any]], str | None]:
    """加载 JSON 文件中的知识条目列表。

    Args:
        filepath: JSON 文件路径。

    Returns:
        (条目列表, 错误信息)。错误信息为 None 表示加载成功。
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        return [], f"无法读取文件 — {exc}"

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return [], f"JSON 解析失败 — {exc}"

    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        return data["items"], None
    if isinstance(data, dict):
        return [data], None

    return [], "顶层不是 JSON 对象、数组或包含 items 的对象"


# ---------------------------------------------------------------------------
# 评分维度实现
# ---------------------------------------------------------------------------


def score_summary_quality(entry: dict[str, Any]) -> DimensionScore:
    """评估摘要质量（满分 25）。

    Args:
        entry: 知识条目。

    Returns:
        DimensionScore 对象。
    """
    max_score = 25.0
    details: list[str] = []
    summary: str = entry.get("summary", "")

    if not summary:
        details.append("摘要为空")
        return DimensionScore("摘要质量", 0.0, max_score, details)

    length = len(summary)

    if length >= 50:
        base = 20.0
        details.append(f"摘要 {length} 字，达到满分标准")
    elif length >= 20:
        base = 15.0
        details.append(f"摘要 {length} 字，达到基本标准")
    else:
        base = 5.0
        details.append(f"摘要仅 {length} 字（< 20），得分较低")

    bonus = 0
    found_keywords: list[str] = []
    summary_lower = summary.lower()
    for kw in TECH_KEYWORDS:
        if kw.lower() in summary_lower:
            found_keywords.append(kw)
            if bonus < 5:
                bonus += 1

    if found_keywords:
        details.append(f"技术关键词奖励 +{bonus}: {', '.join(found_keywords)}")

    score = min(base + bonus, max_score)
    return DimensionScore("摘要质量", score, max_score, details)


def score_tech_depth(entry: dict[str, Any]) -> DimensionScore:
    """评估技术深度（满分 25），基于 score 字段 1-10 映射。

    Args:
        entry: 知识条目。

    Returns:
        DimensionScore 对象。
    """
    max_score = 25.0
    details: list[str] = []

    raw = entry.get("score") or entry.get("relevance_score")

    if raw is None:
        details.append("缺少 score / relevance_score 字段，技术深度评为 0")
        return DimensionScore("技术深度", 0.0, max_score, details)

    if isinstance(raw, (int, float)):
        clamped = max(1.0, min(10.0, float(raw)))
        score = clamped * 2.5
        details.append(f"原始评分 {raw} → 映射得分 {score:.1f}/25")
        return DimensionScore("技术深度", score, max_score, details)

    details.append(f"score 类型错误 ({type(raw).__name__})，技术深度评为 0")
    return DimensionScore("技术深度", 0.0, max_score, details)


def score_format(entry: dict[str, Any]) -> DimensionScore:
    """评估格式规范（满分 20），五项各 4 分。

    Args:
        entry: 知识条目。

    Returns:
        DimensionScore 对象。
    """
    max_score = 20.0
    details: list[str] = []
    score = 0.0
    per_item = 4.0

    eid: str = entry.get("id", "")
    if eid and ID_PATTERN.match(str(eid)):
        score += per_item
    else:
        details.append(f"id 格式无效: '{eid}'")

    title = entry.get("title", "")
    if title and isinstance(title, str):
        score += per_item
    else:
        details.append("title 缺失或为非法类型")

    surl = entry.get("source_url", "")
    if surl and URL_PATTERN.match(str(surl)):
        score += per_item
    else:
        details.append(f"source_url 格式无效: '{surl}'")

    status = entry.get("status", "")
    if status in VALID_STATUSES:
        score += per_item
    else:
        details.append(f"status 值无效: '{status}'")

    created = entry.get("created_at") or entry.get("updated_at")
    if created:
        score += per_item
    else:
        details.append("缺少 created_at / updated_at 时间戳")

    if score == max_score:
        details.append("五项格式检查全部通过")

    return DimensionScore("格式规范", score, max_score, details)


def score_tag_precision(entry: dict[str, Any]) -> DimensionScore:
    """评估标签精度（满分 15）。

    Args:
        entry: 知识条目。

    Returns:
        DimensionScore 对象。
    """
    max_score = 15.0
    details: list[str] = []

    tags: list[str] = entry.get("tags", [])
    if not isinstance(tags, list):
        details.append("tags 不是列表类型")
        return DimensionScore("标签精度", 0.0, max_score, details)

    if not tags:
        details.append("tags 为空")
        return DimensionScore("标签精度", 0.0, max_score, details)

    tag_count = len(tags)

    if 1 <= tag_count <= 3:
        base = 10.0
        details.append(f"{tag_count} 个标签，数量合适")
    else:
        base = 8.0
        details.append(f"{tag_count} 个标签（建议 1-3 个）")

    valid_count = 0
    invalid_tags: list[str] = []
    for tag in tags:
        if tag in VALID_TAGS:
            valid_count += 1
        else:
            invalid_tags.append(tag)

    if invalid_tags:
        details.append(f"存在非标准标签: {', '.join(invalid_tags)}")

    bonus = min(valid_count * 2, 5)
    if bonus:
        details.append(f"{valid_count} 个标准标签，+{bonus}")

    score = min(base + bonus, max_score)
    return DimensionScore("标签精度", score, max_score, details)


def score_buzzword_detection(entry: dict[str, Any]) -> DimensionScore:
    """评估空洞词检测（满分 15），检测中英文空洞词。

    Args:
        entry: 知识条目。

    Returns:
        DimensionScore 对象。
    """
    max_score = 15.0
    details: list[str] = []

    text_fields: list[str] = [
        str(entry.get("title", "")),
        str(entry.get("summary", "")),
        str(entry.get("summary_en", "")),
    ]
    combined = " ".join(text_fields)

    found: list[str] = []
    for word in CHINESE_BUZZWORDS:
        if word in combined:
            found.append(word)
    for word in ENGLISH_BUZZWORDS:
        if word.lower() in combined.lower():
            found.append(word)

    deductions = len(found) * 3
    score = max(0.0, max_score - deductions)

    if not found:
        details.append("未检测到空洞词")
    else:
        details.append(f"检测到空洞词: {', '.join(found)}，-{deductions}")

    return DimensionScore("空洞词检测", score, max_score, details)


# ---------------------------------------------------------------------------
# 主评分逻辑
# ---------------------------------------------------------------------------


def evaluate_entry(entry: dict[str, Any], index: int, filepath: str) -> QualityReport:
    """对单条知识条目进行 5 维度质量评分。

    Args:
        entry: 知识条目。
        index: 条目序号（从 1 开始）。
        filepath: 来源文件路径。

    Returns:
        QualityReport 对象。
    """
    dims = [
        score_summary_quality(entry),
        score_tech_depth(entry),
        score_format(entry),
        score_tag_precision(entry),
        score_buzzword_detection(entry),
    ]

    total = sum(d.score for d in dims)

    if total >= 80:
        grade = "A"
    elif total >= 60:
        grade = "B"
    else:
        grade = "C"

    errors: list[str] = []
    if grade == "C":
        errors.append("综合评级为 C，未达标")
    for d in dims:
        ratio = d.score / d.max_score if d.max_score > 0 else 0
        if ratio < 0.5 and d.score < d.max_score:
            errors.append(f"{d.name} 得分过低 ({d.score:.0f}/{d.max_score:.0f})")

    return QualityReport(
        file=filepath,
        entry_index=index,
        total_score=total,
        grade=grade,
        dimensions=dims,
        errors=errors,
    )


def print_report(report: QualityReport) -> None:
    """打印单条条目的质量报告。

    Args:
        report: QualityReport 对象。
    """
    print(f"\n-- {report.file}  #{report.entry_index} --")
    for dim in report.dimensions:
        ratio = dim.score / dim.max_score if dim.max_score > 0 else 0
        bar = render_bar(ratio)
        print(f"  {bar} {dim.name:　<6} ({dim.score:.0f}/{dim.max_score:.0f})")
        for d in dim.details:
            print(f"       {d}")

    grade_label = {"A": "优秀", "B": "良好", "C": "待改进"}[report.grade]
    print(f"  总分: {report.total_score:.0f}/100  等级: {report.grade} ({grade_label})")
    for err in report.errors:
        print(f"  !! {err}")


def print_summary(reports: list[QualityReport]) -> None:
    """打印汇总统计。

    Args:
        reports: 全部报告列表。
    """
    separator = "=" * 60
    print(f"\n{separator}")

    total = len(reports)
    counts = {"A": 0, "B": 0, "C": 0}
    for r in reports:
        counts[r.grade] += 1

    avg_score = sum(r.total_score for r in reports) / total if total > 0 else 0

    print(f"  评分完成: {total} 个条目")
    print(f"    平均分: {avg_score:.1f}/100")
    print(f"    A (优秀): {counts['A']}   B (良好): {counts['B']}   C (待改进): {counts['C']}")

    if counts["C"]:
        print(f"\n  待改进条目:")
        for r in reports:
            if r.grade == "C":
                print(f"    - {r.file} #{r.entry_index}: {r.total_score:.0f}分")

    print(separator)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """主入口。

    Args:
        argv: 命令行参数列表，默认使用 sys.argv。
    """
    if argv is None:
        argv = sys.argv

    if len(argv) < 2:
        print("用法: python hooks/check_quality.py <json_file> [json_file2 ...]")
        print("支持通配符，如: python hooks/check_quality.py knowledge/articles/*.json")
        sys.exit(0)

    files = collect_files(argv[1:])
    if not files:
        print("错误: 未找到匹配的 JSON 文件", file=sys.stderr)
        sys.exit(1)

    reports: list[QualityReport] = []
    parse_errors: list[str] = []

    for filepath in files:
        entries, error = load_entries(filepath)
        if error:
            parse_errors.append(f"{filepath}: {error}")
            continue

        for i, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                parse_errors.append(f"{filepath}: 条目 #{i} 不是 JSON 对象")
                continue
            report = evaluate_entry(entry, i, str(filepath))
            reports.append(report)
            print_report(report)

    for err in parse_errors:
        print(f"\n!! 解析错误: {err}", file=sys.stderr)

    if not reports:
        print("错误: 未能解析任何有效条目", file=sys.stderr)
        sys.exit(1)

    print_summary(reports)

    has_c = any(r.grade == "C" for r in reports)
    sys.exit(1 if has_c else 0)


if __name__ == "__main__":
    main()
