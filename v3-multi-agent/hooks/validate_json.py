#!/usr/bin/env python3
"""知识条目 JSON 文件校验工具。

支持单文件和多文件输入，校验 JSON 格式、必填字段完整性、字段类型、
ID 格式、状态枚举、URL 格式、摘要长度等。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

VALID_STATUSES = frozenset({"draft", "review", "published", "archived"})
VALID_AUDIENCES = frozenset({"beginner", "intermediate", "advanced"})

ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]+-\d{8}-\d{3}$")
URL_PATTERN = re.compile(r"^https?://")


def collect_files(paths: list[str]) -> list[Path]:
    """收集待校验的 JSON 文件列表，支持通配符。

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


def validate_entry(entry: Any, index: int) -> list[str]:
    """校验单条知识条目。

    Args:
        entry: 待校验的 JSON 对象。
        index: 条目序号（从 1 开始）。

    Returns:
        错误信息列表，空列表表示校验通过。
    """
    errors: list[str] = []

    if not isinstance(entry, dict):
        errors.append(f"条目 #{index}: 不是 JSON 对象")
        return errors

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in entry:
            errors.append(f"条目 #{index}: 缺少必填字段 '{field}'")
        elif not isinstance(entry[field], expected_type):
            actual = type(entry[field]).__name__
            expected = expected_type.__name__
            errors.append(
                f"条目 #{index}: 字段 '{field}' 类型错误，"
                f"期望 {expected}，实际 {actual}"
            )

    if errors:
        return errors

    eid: str = entry["id"]
    if not ID_PATTERN.match(eid):
        errors.append(
            f"条目 #{index}: ID 格式错误 '{eid}'，"
            f"应为 {{source}}-{{YYYYMMDD}}-{{NNN}}"
        )

    status: str = entry["status"]
    if status not in VALID_STATUSES:
        errors.append(
            f"条目 #{index}: status 值无效 '{status}'，"
            f"合法值: {', '.join(sorted(VALID_STATUSES))}"
        )

    surl: str = entry["source_url"]
    if not URL_PATTERN.match(surl):
        errors.append(
            f"条目 #{index}: source_url 格式无效 '{surl}'，"
            f"必须以 http:// 或 https:// 开头"
        )

    summary: str = entry["summary"]
    if len(summary) < 20:
        errors.append(
            f"条目 #{index}: summary 长度不足（{len(summary)} 字），"
            f"最少 20 字"
        )

    tags: list = entry["tags"]
    if len(tags) < 1:
        errors.append(
            f"条目 #{index}: tags 不能为空，至少需要 1 个标签"
        )

    if "score" in entry:
        score = entry["score"]
        if not isinstance(score, (int, float)):
            errors.append(
                f"条目 #{index}: score 类型错误，"
                f"期望 int/float，实际 {type(score).__name__}"
            )
        elif score < 1 or score > 10:
            errors.append(
                f"条目 #{index}: score 值 {score} 超出范围 1-10"
            )

    if "audience" in entry:
        audience = entry["audience"]
        if audience not in VALID_AUDIENCES:
            errors.append(
                f"条目 #{index}: audience 值无效 '{audience}'，"
                f"合法值: {', '.join(sorted(VALID_AUDIENCES))}"
            )

    return errors


def validate_file(filepath: Path) -> tuple[int, int, list[str]]:
    """校验单个 JSON 文件。

    Args:
        filepath: JSON 文件路径。

    Returns:
        (条目总数, 错误数, 错误信息列表)
    """
    all_errors: list[str] = []
    total = 0

    try:
        content = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        return 0, 1, [f"{filepath}: 无法读取文件 — {exc}"]

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return 0, 1, [f"{filepath}: JSON 解析失败 — {exc}"]

    entries: list[Any]
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        entries = data["items"]
    elif isinstance(data, dict):
        entries = [data]
    else:
        return 0, 1, [f"{filepath}: 顶层不是 JSON 对象、数组或包含 items 的对象"]

    for i, entry in enumerate(entries, start=1):
        total += 1
        item_errors = validate_entry(entry, i)
        for err in item_errors:
            all_errors.append(f"  {filepath}: {err}")

    error_count = len(all_errors)
    return total, error_count, all_errors


def main(argv: list[str] | None = None) -> None:
    """主入口。

    Args:
        argv: 命令行参数列表，默认使用 sys.argv。
    """
    if argv is None:
        argv = sys.argv

    if len(argv) < 2:
        print("用法: python hooks/validate_json.py <json_file> [json_file2 ...]")
        print("支持通配符，如: python hooks/validate_json.py knowledge/articles/*.json")
        sys.exit(0)

    files = collect_files(argv[1:])
    if not files:
        print("错误: 未找到匹配的 JSON 文件", file=sys.stderr)
        sys.exit(1)

    total_files = 0
    total_entries = 0
    total_errors = 0
    all_errors: list[str] = []

    for filepath in files:
        total_files += 1
        entries, errors, err_msgs = validate_file(filepath)
        total_entries += entries
        total_errors += errors
        all_errors.extend(err_msgs)

    for msg in all_errors:
        print(msg, file=sys.stderr)

    separator = "=" * 60
    print(f"\n{separator}", file=sys.stderr)
    print(f"  校验完成: {total_files} 个文件, {total_entries} 个条目", file=sys.stderr)

    if total_errors:
        print(f"  ❌ 发现 {total_errors} 个错误", file=sys.stderr)
        print(separator, file=sys.stderr)
        sys.exit(1)

    print(f"  ✅ 全部通过", file=sys.stderr)
    print(separator, file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
