#!/usr/bin/env python3
"""知识条目推送模块。

提供 OOP 架构的多渠道异步推送能力，支持 Telegram Bot API
（MarkdownV2）和飞书 Webhook（交互式卡片），统一入口并发
发布每日简报到所有已配置渠道。
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp

# 将项目根目录加入 sys.path，使 distribution.formatter 可被导入
import sys

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from distribution.formatter import generate_daily_digest  # noqa: E402

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class PublishResult:
    """单次发布结果。

    Attributes:
        channel: 发布渠道标识（telegram / feishu）。
        success: 是否发布成功。
        message_id: 平台返回的消息 ID，失败时为 None。
        error: 失败原因，成功时为 None。
    """

    channel: str
    success: bool
    message_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------


class BasePublisher(ABC):
    """推送器抽象基类。

    所有渠道推送器必须实现 send_message 和 send_digest 方法。
    子类通过 _format_key 指定需要从 generate_daily_digest()
    返回值中提取的格式键。
    """

    _format_key: str = ""

    @abstractmethod
    async def send_message(self, content: Any, **kwargs: Any) -> PublishResult:
        """发送单条消息到渠道。

        Args:
            content: 消息内容，类型取决于渠道。
            **kwargs: 渠道特定的额外参数。

        Returns:
            PublishResult 发布结果。
        """
        ...

    @abstractmethod
    async def send_digest(
        self,
        date_str: str | None = None,
        top_n: int = 5,
        knowledge_dir: str = "knowledge/articles",
    ) -> list[PublishResult]:
        """生成并发送当日简报。

        Args:
            date_str: 日期字符串 YYYY-MM-DD，默认今天。
            top_n: 取 Top N 条。
            knowledge_dir: 知识条目目录路径。

        Returns:
            PublishResult 列表，每篇发送的条目一个结果。
        """
        ...


# ---------------------------------------------------------------------------
# Telegram 推送器
# ---------------------------------------------------------------------------


class TelegramPublisher(BasePublisher):
    """通过 Telegram Bot API 发送 MarkdownV2 消息。

    环境变量：
        TELEGRAM_BOT_TOKEN: Bot Token。
        TELEGRAM_CHAT_ID: 目标 Chat ID。
    """

    _format_key = "telegram"

    def __init__(self) -> None:
        """初始化 Telegram 推送器，从环境变量读取凭据。"""
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self._configured = bool(self._token and self._chat_id)

    @property
    def configured(self) -> bool:
        """凭据是否已配置。"""
        return self._configured

    async def send_message(self, content: str, **kwargs: Any) -> PublishResult:
        """通过 Telegram Bot API 发送 MarkdownV2 消息。

        Args:
            content: MarkdownV2 格式文本。
            **kwargs: 传递给 Telegram API 的额外参数。

        Returns:
            PublishResult 发布结果。
        """
        if not self._configured:
            return PublishResult(
                channel="telegram",
                success=False,
                error="TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未配置",
            )

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": content,
            "parse_mode": "MarkdownV2",
            **kwargs,
        }

        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return PublishResult(
                channel="telegram",
                success=False,
                error=f"网络请求失败: {exc}",
            )

        if data.get("ok"):
            return PublishResult(
                channel="telegram",
                success=True,
                message_id=str(data.get("result", {}).get("message_id", "")),
            )

        return PublishResult(
            channel="telegram",
            success=False,
            error=data.get("description", "未知错误"),
        )

    async def send_digest(
        self,
        date_str: str | None = None,
        top_n: int = 5,
        knowledge_dir: str = "knowledge/articles",
    ) -> list[PublishResult]:
        """生成并发送当日 Telegram 日报。

        将整份日报作为单条 MarkdownV2 消息发送。

        Args:
            date_str: 日期字符串。
            top_n: Top N 条目数。
            knowledge_dir: 知识条目目录。

        Returns:
            单个 PublishResult 的列表。
        """
        if not self._configured:
            return [
                PublishResult(
                    channel="telegram",
                    success=False,
                    error="TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未配置",
                )
            ]

        digest = generate_daily_digest(
            knowledge_dir=knowledge_dir, date_str=date_str, top_n=top_n
        )
        result = await self.send_message(digest[self._format_key])
        return [result]


# ---------------------------------------------------------------------------
# 飞书推送器
# ---------------------------------------------------------------------------


class FeishuPublisher(BasePublisher):
    """通过飞书 Webhook 发送交互式卡片消息。

    环境变量：
        FEISHU_WEBHOOK_URL: 飞书机器人 Webhook 地址。
    """

    _format_key = "feishu"

    def __init__(self) -> None:
        """初始化飞书推送器，从环境变量读取 Webhook URL。"""
        self._webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "")
        self._configured = bool(self._webhook_url)

    @property
    def configured(self) -> bool:
        """Webhook URL 是否已配置。"""
        return self._configured

    async def send_message(self, content: dict[str, Any], **kwargs: Any) -> PublishResult:
        """通过飞书 Webhook 发送单张交互式卡片。

        Args:
            content: 飞书卡片消息体 dict（含 msg_type 和 card）。
            **kwargs: 额外参数（保留兼容性）。

        Returns:
            PublishResult 发布结果。
        """
        _ = kwargs  # 飞书 Webhook 无额外参数需求

        if not self._configured:
            return PublishResult(
                channel="feishu",
                success=False,
                error="FEISHU_WEBHOOK_URL 未配置",
            )

        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self._webhook_url,
                    json=content,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                ) as resp:
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return PublishResult(
                channel="feishu",
                success=False,
                error=f"网络请求失败: {exc}",
            )

        if data.get("code") == 0 or data.get("StatusCode") == 0:
            return PublishResult(
                channel="feishu",
                success=True,
            )

        return PublishResult(
            channel="feishu",
            success=False,
            error=data.get("msg", data.get("message", "未知错误")),
        )

    async def send_digest(
        self,
        date_str: str | None = None,
        top_n: int = 5,
        knowledge_dir: str = "knowledge/articles",
    ) -> list[PublishResult]:
        """生成并发送当日飞书日报。

        每篇文章作为一张独立卡片依次发送。

        Args:
            date_str: 日期字符串。
            top_n: Top N 条目数。
            knowledge_dir: 知识条目目录。

        Returns:
            PublishResult 列表，每张卡片一个结果。
        """
        if not self._configured:
            return [
                PublishResult(
                    channel="feishu",
                    success=False,
                    error="FEISHU_WEBHOOK_URL 未配置",
                )
            ]

        digest = generate_daily_digest(
            knowledge_dir=knowledge_dir, date_str=date_str, top_n=top_n
        )
        cards: list[dict[str, Any]] = digest.get(self._format_key, [])

        if not cards:
            return [
                PublishResult(
                    channel="feishu",
                    success=True,
                    error="当日无内容需推送",
                )
            ]

        results: list[PublishResult] = []
        for card in cards:
            result = await self.send_message(card)
            results.append(result)

        return results


# ---------------------------------------------------------------------------
# QQ 推送器
# ---------------------------------------------------------------------------


class QQPublisher(BasePublisher):
    """通过 QQ Bot API 发送 Markdown 消息。

    环境变量：
        AppID: QQ Bot AppID。
        AppSecret: QQ Bot AppSecret。
        QQ_TARGET_ID: 目标 QQ 用户 openid。
    """

    _format_key = "qq"
    _TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
    _MSG_URL = "https://api.sgroup.qq.com/v2/users/{openid}/messages"

    def __init__(self) -> None:
        """初始化 QQ 推送器，从环境变量读取凭据。"""
        self._app_id = os.getenv("AppID", "")
        self._app_secret = os.getenv("AppSecret", "")
        self._target_id = os.getenv("QQ_TARGET_ID", "")
        self._configured = bool(self._app_id and self._app_secret and self._target_id)
        self._token: str | None = None
        self._token_expiry: float = 0

    @property
    def configured(self) -> bool:
        """凭据是否已配置。"""
        return self._configured

    async def _get_access_token(self) -> str:
        """获取 QQ Bot access_token，带缓存。

        Returns:
            access_token 字符串。

        Raises:
            RuntimeError: 获取 token 失败。
        """
        import time

        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token

        timeout = aiohttp.ClientTimeout(total=30)
        payload = {"appId": self._app_id, "clientSecret": self._app_secret}
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self._TOKEN_URL, json=payload) as resp:
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise RuntimeError(f"获取 QQ access_token 网络错误: {exc}")

        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"获取 QQ access_token 失败: {data}")

        self._token = token
        self._token_expiry = now + int(data.get("expires_in", 7200)) - 300
        return token

    async def send_message(self, content: str, **kwargs: Any) -> PublishResult:
        """通过 QQ Bot API 发送 Markdown 消息。

        Args:
            content: Markdown 格式文本。
            **kwargs: 额外参数（保留兼容性）。

        Returns:
            PublishResult 发布结果。
        """
        _ = kwargs

        if not self._configured:
            return PublishResult(
                channel="qq",
                success=False,
                error="QQ Bot 未配置（需设置 AppID、AppSecret、QQ_TARGET_ID）",
            )

        try:
            token = await self._get_access_token()
        except RuntimeError as exc:
            return PublishResult(channel="qq", success=False, error=str(exc))

        url = self._MSG_URL.format(openid=self._target_id)
        payload: dict[str, Any] = {
            "msg_type": 2,
            "markdown": {"content": content},
        }

        timeout = aiohttp.ClientTimeout(total=30)
        headers = {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return PublishResult(
                channel="qq", success=False, error=f"网络请求失败: {exc}"
            )

        msg_id = data.get("id", "")
        err_code = data.get("code")
        if msg_id and err_code is None:
            return PublishResult(
                channel="qq",
                success=True,
                message_id=msg_id,
            )
        return PublishResult(
            channel="qq",
            success=False,
            error=data.get("message", f"错误码 {err_code}"),
        )

    async def send_digest(
        self,
        date_str: str | None = None,
        top_n: int = 5,
        knowledge_dir: str = "knowledge/articles",
    ) -> list[PublishResult]:
        """生成并发送当日 QQ 日报。

        将整份日报作为单条 Markdown 消息发送。

        Args:
            date_str: 日期字符串。
            top_n: Top N 条目数。
            knowledge_dir: 知识条目目录。

        Returns:
            单个 PublishResult 的列表。
        """
        if not self._configured:
            return [
                PublishResult(
                    channel="qq",
                    success=False,
                    error="QQ Bot 未配置",
                )
            ]

        digest = generate_daily_digest(
            knowledge_dir=knowledge_dir, date_str=date_str, top_n=top_n
        )
        result = await self.send_message(digest[self._format_key])
        return [result]


# ---------------------------------------------------------------------------
# 微信推送器
# ---------------------------------------------------------------------------


class WeChatPublisher(BasePublisher):
    """通过企业微信 API 发送 Markdown 消息。

    环境变量：
        WECOM_CORP_ID: 企业 ID。
        WECOM_CORP_SECRET: 应用 Secret。
        WECOM_AGENT_ID: 应用 AgentId。
        chat_id / WECOM_TO_USER: 接收消息的用户 ID。
    """

    _format_key = "wechat"
    _TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
    _MSG_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"

    def __init__(self) -> None:
        """初始化微信推送器，从环境变量读取凭据。"""
        self._corp_id = os.getenv("WECOM_CORP_ID", "")
        self._corp_secret = os.getenv("WECOM_CORP_SECRET", "")
        self._agent_id = os.getenv("WECOM_AGENT_ID", "")
        self._to_user = os.getenv("WECOM_TO_USER") or os.getenv("chat_id", "")
        self._configured = bool(
            self._corp_id and self._corp_secret and self._agent_id and self._to_user
        )
        self._token: str | None = None
        self._token_expiry: float = 0

    @property
    def configured(self) -> bool:
        """凭据是否已配置。"""
        return self._configured

    async def _get_access_token(self) -> str:
        """获取企业微信 access_token，带缓存。

        Returns:
            access_token 字符串。

        Raises:
            RuntimeError: 获取 token 失败。
        """
        import time

        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token

        timeout = aiohttp.ClientTimeout(total=30)
        params = {"corpid": self._corp_id, "corpsecret": self._corp_secret}
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._TOKEN_URL, params=params) as resp:
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise RuntimeError(f"获取企业微信 access_token 网络错误: {exc}")

        if data.get("errcode", -1) != 0:
            raise RuntimeError(
                f"获取企业微信 access_token 失败: {data.get('errmsg', data)}"
            )

        self._token = data["access_token"]
        self._token_expiry = now + int(data.get("expires_in", 7200)) - 300
        return self._token

    async def send_message(self, content: str, **kwargs: Any) -> PublishResult:
        """通过企业微信 API 发送 Markdown 消息。

        Args:
            content: Markdown 格式文本。
            **kwargs: 额外参数（保留兼容性）。

        Returns:
            PublishResult 发布结果。
        """
        _ = kwargs

        if not self._configured:
            return PublishResult(
                channel="wechat",
                success=False,
                error="企业微信未配置",
            )

        try:
            token = await self._get_access_token()
        except RuntimeError as exc:
            return PublishResult(
                channel="wechat", success=False, error=str(exc)
            )

        url = f"{self._MSG_URL}?access_token={token}"
        payload: dict[str, Any] = {
            "touser": self._to_user,
            "msgtype": "markdown",
            "agentid": int(self._agent_id),
            "markdown": {"content": content},
        }

        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return PublishResult(
                channel="wechat", success=False, error=f"网络请求失败: {exc}"
            )

        if data.get("errcode") == 0:
            return PublishResult(
                channel="wechat",
                success=True,
                message_id=data.get("msgid", ""),
            )
        return PublishResult(
            channel="wechat",
            success=False,
            error=data.get("errmsg", "未知错误"),
        )

    async def send_digest(
        self,
        date_str: str | None = None,
        top_n: int = 5,
        knowledge_dir: str = "knowledge/articles",
    ) -> list[PublishResult]:
        """生成并发送当日微信日报。

        将整份日报作为单条 Markdown 消息发送。

        Args:
            date_str: 日期字符串。
            top_n: Top N 条目数。
            knowledge_dir: 知识条目目录。

        Returns:
            单个 PublishResult 的列表。
        """
        if not self._configured:
            return [
                PublishResult(
                    channel="wechat",
                    success=False,
                    error="企业微信未配置（需设置 WECOM_CORP_ID、WECOM_CORP_SECRET、WECOM_AGENT_ID、chat_id）",
                )
            ]

        digest = generate_daily_digest(
            knowledge_dir=knowledge_dir, date_str=date_str, top_n=top_n
        )
        result = await self.send_message(digest[self._format_key])
        return [result]


# ---------------------------------------------------------------------------
# 统一异步入口
# ---------------------------------------------------------------------------


async def publish_daily_digest(
    date_str: str | None = None,
    top_n: int = 5,
    knowledge_dir: str = "knowledge/articles",
) -> list[PublishResult]:
    """统一异步入口：生成日报并并发发布到所有已配置渠道。

    异步获取凭据有效且已配置的推送器，并发调用 send_digest。

    Args:
        date_str: 日期字符串 YYYY-MM-DD，默认今天。
        top_n: 取 Top N 条。
        knowledge_dir: 知识条目目录路径。

    Returns:
        所有渠道的 PublishResult 列表（已扁平化）。
    """
    publishers: list[BasePublisher] = [
        pub
        for pub in (
            TelegramPublisher(),
            FeishuPublisher(),
            QQPublisher(),
            WeChatPublisher(),
        )
        if pub.configured
    ]

    if not publishers:
        return [
            PublishResult(
                channel="global",
                success=False,
                error="没有配置任何推送渠道（请设置 TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID / FEISHU_WEBHOOK_URL / AppID + AppSecret + QQ_TARGET_ID / WECOM_CORP_ID + WECOM_CORP_SECRET + WECOM_AGENT_ID + chat_id）",
            )
        ]

    coros = [
        pub.send_digest(date_str=date_str, top_n=top_n, knowledge_dir=knowledge_dir)
        for pub in publishers
    ]
    nested = await asyncio.gather(*coros, return_exceptions=True)

    results: list[PublishResult] = []
    for item in nested:
        if isinstance(item, BaseException):
            results.append(
                PublishResult(
                    channel="global",
                    success=False,
                    error=f"发布异常: {item}",
                )
            )
        elif isinstance(item, list):
            results.extend(item)

    return results
