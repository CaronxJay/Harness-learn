#!/usr/bin/env python3
"""JSON 格式校验脚本

用于校验知识条目 JSON 文件是否符合定义的 Schema。

使用方法：
    python3 hooks/validate_json.py <json_file> [json_file2 ...]
    python3 hooks/validate_json.py knowledge/articles/*.json

校验规则：
    1. JSON 解析检查
    2. JSON Schema 校验（使用 specs/schemas/ 下的 Schema 文件）
    3. ID 格式检查（{source}-{YYYYMMDD}-{NNN}）
    4. URL 格式检查（https?://...）
    5. 摘要长度检查（最少 20 字）
    6. 标签数量检查（至少 1 个）
    7. score 范围检查（1-10，可选）
    8. audience 枚举检查（beginner/intermediate/advanced，可选）

编码规范：
    - 遵循 PEP 8
    - 使用 pathlib
    - 使用 jsonschema 库进行 Schema 校验
"""

import json
import re
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("错误: 缺少 jsonschema 库，请运行: pip install jsonschema")
    sys.exit(1)


# Schema 文件路径
SCHEMA_DIR: Path = Path(__file__).parent.parent / "specs" / "schemas"
RAW_SCHEMA_FILE: Path = SCHEMA_DIR / "raw.json"
ARTICLE_SCHEMA_FILE: Path = SCHEMA_DIR / "article.json"

# 自定义校验规则
ID_PATTERN: re.Pattern = re.compile(r"^(github|hackernews)-\d{8}-\d{3}$")
URL_PATTERN: re.Pattern = re.compile(r"^https?://\S+$")
MIN_SUMMARY_LENGTH: int = 20
MIN_TAGS_COUNT: int = 1
SCORE_MIN: int = 1
SCORE_MAX: int = 10
VALID_AUDIENCE: set[str] = {"beginner", "intermediate", "advanced"}


class ValidationError:
    """校验错误"""

    def __init__(self, file_path: Path, field: str, message: str):
        self.file_path = file_path
        self.field = field
        self.message = message

    def __str__(self) -> str:
        return f"{self.file_path}: {self.field} - {self.message}"


def load_schema(schema_file: Path) -> dict:
    """加载 JSON Schema"""
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema 文件不存在: {schema_file}")

    with open(schema_file, "r", encoding="utf-8") as f:
        return json.load(f)


def detect_schema_type(data: any) -> str:
    """自动检测 Schema 类型

    Returns:
        "raw" 或 "article"
    """
    if isinstance(data, list):
        return "raw"
    else:
        return "article"


def validate_json_parse(file_path: Path) -> tuple[any, list[ValidationError]]:
    """检查 JSON 是否能正确解析

    Returns:
        (解析后的数据, 错误列表)
    """
    errors: list[ValidationError] = []

    if not file_path.exists():
        errors.append(ValidationError(file_path, "_file", "文件不存在"))
        return None, errors

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(ValidationError(file_path, "_json", f"JSON 解析失败: {e}"))
        return None, errors

    return data, errors


def validate_schema(data: any, schema: dict, file_path: Path) -> list[ValidationError]:
    """使用 JSON Schema 校验数据

    Returns:
        错误列表
    """
    errors: list[ValidationError] = []

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "_root"
        errors.append(ValidationError(file_path, path, f"Schema 校验失败: {e.message}"))
    except jsonschema.SchemaError as e:
        errors.append(ValidationError(file_path, "_schema", f"Schema 错误: {e.message}"))

    return errors


def validate_custom_rules(entry: dict, file_path: Path, index: int | None = None) -> list[ValidationError]:
    """校验自定义规则

    Args:
        entry: 条目数据
        file_path: 文件路径
        index: 条目索引（数组中的位置）

    Returns:
        错误列表
    """
    errors: list[ValidationError] = []
    prefix = f"[{index}]" if index is not None else ""

    # 1. ID 格式检查
    if "id" in entry and isinstance(entry["id"], str):
        if not ID_PATTERN.match(entry["id"]):
            errors.append(ValidationError(
                file_path,
                f"{prefix}id",
                f"ID 格式错误: 期望 {{source}}-{{YYYYMMDD}}-{{NNN}}，实际 '{entry['id']}'"
            ))

    # 2. URL 格式检查
    if "source_url" in entry and isinstance(entry["source_url"], str):
        if not URL_PATTERN.match(entry["source_url"]):
            errors.append(ValidationError(
                file_path,
                f"{prefix}source_url",
                f"URL 格式错误: '{entry['source_url']}'"
            ))
    elif "url" in entry and isinstance(entry["url"], str):
        if not URL_PATTERN.match(entry["url"]):
            errors.append(ValidationError(
                file_path,
                f"{prefix}url",
                f"URL 格式错误: '{entry['url']}'"
            ))

    # 3. 摘要长度检查
    if "summary" in entry and isinstance(entry["summary"], str):
        if len(entry["summary"]) < MIN_SUMMARY_LENGTH:
            errors.append(ValidationError(
                file_path,
                f"{prefix}summary",
                f"摘要过短: 期望至少 {MIN_SUMMARY_LENGTH} 字，实际 {len(entry['summary'])} 字"
            ))

    # 4. 标签数量检查
    if "tags" in entry and isinstance(entry["tags"], list):
        if len(entry["tags"]) < MIN_TAGS_COUNT:
            errors.append(ValidationError(
                file_path,
                f"{prefix}tags",
                f"标签数量不足: 期望至少 {MIN_TAGS_COUNT} 个，实际 {len(entry['tags'])} 个"
            ))

    # 5. score 范围检查（可选）
    if "score" in entry:
        if not isinstance(entry["score"], (int, float)):
            errors.append(ValidationError(
                file_path,
                f"{prefix}score",
                f"score 类型错误: 期望 int/float，实际 {type(entry['score']).__name__}"
            ))
        elif not (SCORE_MIN <= entry["score"] <= SCORE_MAX):
            errors.append(ValidationError(
                file_path,
                f"{prefix}score",
                f"score 范围错误: 期望 {SCORE_MIN}-{SCORE_MAX}，实际 {entry['score']}"
            ))

    # 6. audience 枚举检查（可选）
    if "audience" in entry:
        if not isinstance(entry["audience"], str):
            errors.append(ValidationError(
                file_path,
                f"{prefix}audience",
                f"audience 类型错误: 期望 str，实际 {type(entry['audience']).__name__}"
            ))
        elif entry["audience"] not in VALID_AUDIENCE:
            errors.append(ValidationError(
                file_path,
                f"{prefix}audience",
                f"audience 值无效: 期望 {VALID_AUDIENCE}，实际 '{entry['audience']}'"
            ))

    return errors


def validate_file(file_path: Path, schema_type: str = "auto") -> list[ValidationError]:
    """校验单个文件

    Args:
        file_path: JSON 文件路径
        schema_type: Schema 类型 ("raw", "article", "auto")

    Returns:
        错误列表
    """
    # 解析 JSON
    data, errors = validate_json_parse(file_path)
    if errors:
        return errors

    # 自动检测 Schema 类型
    if schema_type == "auto":
        schema_type = detect_schema_type(data)

    # 加载 Schema
    try:
        if schema_type == "raw":
            schema = load_schema(RAW_SCHEMA_FILE)
        elif schema_type == "article":
            schema = load_schema(ARTICLE_SCHEMA_FILE)
        else:
            errors.append(ValidationError(file_path, "_schema", f"未知的 Schema 类型: {schema_type}"))
            return errors
    except FileNotFoundError as e:
        errors.append(ValidationError(file_path, "_schema", str(e)))
        return errors

    # Schema 校验
    schema_errors = validate_schema(data, schema, file_path)
    errors.extend(schema_errors)

    # 自定义规则校验
    if isinstance(data, list):
        for i, entry in enumerate(data):
            if isinstance(entry, dict):
                custom_errors = validate_custom_rules(entry, file_path, i)
                errors.extend(custom_errors)
    elif isinstance(data, dict):
        custom_errors = validate_custom_rules(data, file_path)
        errors.extend(custom_errors)

    return errors


def main() -> int:
    """主函数

    Returns:
        0: 校验通过
        1: 校验失败
    """
    # 检查参数
    if len(sys.argv) < 2:
        print("用法: python3 hooks/validate_json.py <json_file> [json_file2 ...]")
        print("示例: python3 hooks/validate_json.py knowledge/articles/*.json")
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
        print("错误: 没有找到要校验的文件")
        return 1

    # 校验所有文件
    all_errors: list[ValidationError] = []
    file_count = len(file_paths)
    error_file_count = 0

    for file_path in sorted(file_paths):
        errors = validate_file(file_path)
        if errors:
            error_file_count += 1
            all_errors.extend(errors)

    # 输出结果
    if all_errors:
        print(f"\n校验失败: {error_file_count}/{file_count} 个文件有错误\n")
        print("错误列表:")
        print("-" * 80)
        for error in all_errors:
            print(f"  {error}")
        print("-" * 80)
        print(f"\n汇总: {len(all_errors)} 个错误，{error_file_count} 个文件失败")
        return 1
    else:
        print(f"校验通过: {file_count} 个文件全部通过")
        return 0


if __name__ == "__main__":
    sys.exit(main())
