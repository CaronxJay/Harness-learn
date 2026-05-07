"""pytest 全局配置 — 注册自定义标记、加载 .env。"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

# 屏蔽 PytestUnknownMarkWarning（避免自定义 slow 标记触发警告）
warnings.filterwarnings("ignore", message=".*Unknown pytest\\.mark\\.slow.*")

# 加载项目根目录的 .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)


def pytest_configure(config: object) -> None:
    """注册自定义 pytest 标记。"""
    config.addinivalue_line(  # type: ignore[union-attr]
        "markers",
        "slow: 标记依赖 LLM 调用的慢速测试，可通过 -m 'not slow' 跳过",
    )
