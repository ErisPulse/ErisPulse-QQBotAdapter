import asyncio
import base64
import hashlib
import json
import os
import random
import re
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ErisPulse import sdk
from ErisPulse.Core import client
from ErisPulse.Core.Bases import BaseConfig, BotAccountConfig
from ErisPulse.Core.Bases.errors import (
    ClientConnectionError,
    ClientError,
    ClientTimeoutError,
)

from .Converter import QQBotConverter
from .WebSocket import QQBotWebSocket

try:
    from ErisPulse.runtime.tasks import spawn_background
except ImportError:  # pragma: no cover
    spawn_background = None

__version__ = "5.0.0"

# 软依赖的框架最低版本（运行时检测，仅提示不强制）
MIN_FRAMEWORK_VERSION = (2, 7, 1)

DEFAULT_API_BASE_URL = "https://api.bot.qq.com"
DEFAULT_ACCESS_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
FALLBACK_GATEWAY_URL = "wss://api.sgroup.qq.com/websocket/"
TOKEN_REFRESH_BUFFER = 45  # 提前45秒刷新 token
TOKEN_RETRY_TIMES = 3

CHUNK_THRESHOLD = 5 * 1024 * 1024  # 超过5MB走分片上传
REGISTRY_MAX = 800

INTENT_BITS = {
    "GUILDS": 0,
    "GUILD_MEMBERS": 1,
    "GUILD_MESSAGES": 9,
    "GUILD_MESSAGE_REACTIONS": 10,
    "DIRECT_MESSAGE": 12,
    "GROUP_MEMBER": 24,
    "GROUP_AND_C2C_EVENT": 25,
    "INTERACTION": 26,
    "MESSAGE_AUDIT": 27,
    "FORUMS_EVENT": 28,
    "AUDIO_ACTION": 29,
    "PUBLIC_GUILD_MESSAGES": 30,
}

DEFAULT_INTENTS = "[0, 9, 12, 25, 26, 27]"

DEFAULT_FILE_NAMES = {1: "image.png", 2: "video.mp4", 3: "audio.silk", 4: "file.bin"}

_EXTENSION_FILE_TYPES = {
    ".png": 1, ".jpg": 1, ".jpeg": 1, ".gif": 1, ".webp": 1, ".bmp": 1,
    ".mp4": 2, ".mov": 2, ".avi": 2, ".mkv": 2, ".flv": 2,
    ".silk": 3, ".mp3": 3, ".wav": 3, ".ogg": 3, ".m4a": 3, ".amr": 3, ".aac": 3,
}

SEGMENT_FILE_TYPES = {
    "image": 1,
    "video": 2,
    "voice": 3,
    "audio": 3,
    "file": 4,
}


@dataclass
class QQBotConfig(BotAccountConfig):
    """QQBot 账户配置"""

    appid: str = field(
        default="",
        metadata={
            "description": "QQ机器人应用ID（QQ开放平台获取）",
            "required": True,
            "ui": {"widget": "text", "group": "basic", "order": 1},
        },
    )
    secret: str = field(
        default="",
        metadata={
            "description": "QQ机器人客户端密钥（QQ开放平台获取）",
            "required": True,
            "secret": True,
            "ui": {"widget": "password", "group": "basic", "order": 2},
        },
    )
    mode: str = field(
        default="websocket",
        metadata={
            "description": "事件接收方式：websocket=长连接，webhook=HTTP回调",
            "ui": {
                "widget": "select",
                "group": "connection",
                "order": 3,
                "options": [
                    {"label": "WebSocket 长连接", "value": "websocket"},
                    {"label": "Webhook 回调", "value": "webhook"},
                ],
            },
        },
    )
    api_base_url: str = field(
        default=DEFAULT_API_BASE_URL,
        metadata={
            "description": "OpenAPI 根地址（默认官方地址，可自定义用于代理）",
            "ui": {"widget": "text", "group": "advanced", "order": 4},
        },
    )
    access_token_url: str = field(
        default="",
        metadata={
            "description": "自定义 access_token 接口地址（留空使用官方接口）",
            "ui": {"widget": "text", "group": "advanced", "order": 5},
        },
    )
    gateway_url: str = field(
        default="",
        metadata={
            "description": "WebSocket 网关地址（留空时通过 /gateway/bot 动态获取）",
            "ui": {"widget": "text", "group": "connection", "order": 6},
        },
    )
    webhook_path: str = field(
        default="/webhook",
        metadata={
            "description": "Webhook 模式的回调路径（mode=webhook 时生效）",
            "ui": {"widget": "text", "group": "connection", "order": 7},
        },
    )
    bot_id: str = field(
        default="",
        metadata={
            "description": "机器人ID（留空时连接后自动获取，也可手动填写用于 Using() 定位账户）",
            "ui": {"widget": "text", "group": "basic", "order": 8},
        },
    )
    sandbox: bool = field(
        default=False,
        metadata={
            "description": "[已废弃] 官方已统一使用 api.bot.qq.com，此字段仅用于兼容旧配置",
            "ui": {"widget": "switch", "group": "advanced", "order": 99},
        },
    )


@dataclass
class QQBotAdapterConfig(BaseConfig):
    """QQBot 适配器全局配置"""

    intents: str = field(
        default=DEFAULT_INTENTS,
        metadata={
            "description": (
                "订阅的 intents（JSON数组）：支持事件位序号（如 25）或事件名（如 \"GROUP_AND_C2C_EVENT\"）。"
                "常用位：0=GUILDS 9=GUILD_MESSAGES 12=DIRECT_MESSAGE 24=GROUP_MEMBER 25=群/私聊 26=INTERACTION 27=MESSAGE_AUDIT"
            ),
            "ui": {"widget": "text", "group": "connection", "order": 1},
        },
    )


class _AccountRuntime:
    """单个账户的运行时状态（token / 连接 / 机器人信息）"""

    __slots__ = (
        "name",
        "config",
        "token",
        "token_expires",
        "bot_id",
        "user_name",
        "ws",
        "webhook",
    )

    def __init__(self, name: str, config: QQBotConfig):
        self.name = name
        self.config = config
        self.token: str = ""
        self.token_expires: float = 0.0
        self.bot_id: str = ""
        self.user_name: str = ""
        self.ws: Optional[QQBotWebSocket] = None
        self.webhook: Any = None

    @property
    def online(self) -> bool:
        if self.ws is not None:
            return self.ws.connected
        if self.webhook is not None:
            return self.webhook.registered
        return False


class QQBotAdapter(sdk.BaseAdapter):
    """
    QQ官方机器人适配器（v5）

    - 对齐官方 API：api.bot.qq.com + X-Union-Appid
    - 多账户并行（WebSocket / Webhook 混合模式）
    - OneBot12 标准 Api DSL（信息查询 / 撤回 / 元动作）
    - Request DSL（GROUP_JOIN_REQUEST 入群申请审批）
    - 平台原生API方法族（群管理 / 菜单面板 / 流式消息 / 分片上传 / 频道全功能等）
    """

    _platform = "qqbot"
    AccountConfigClass = QQBotConfig
    ConfigClass = QQBotAdapterConfig

    # ==================== OneBot12 标准动作 → 平台端点路由表 ====================

    _OB12_ROUTES: Dict[str, Tuple[str, str]] = {
        "get_self_info": ("GET", "/users/@me"),
        "get_group_info": ("GET", "/v2/groups/{group_id}/info"),
        "get_group_member_info": ("GET", "/v2/groups/{group_id}/members/{user_id}"),
        "get_group_member_list": ("GET", "/v2/groups/{group_id}/members"),
        "get_guild_info": ("GET", "/guilds/{guild_id}"),
        "get_guild_list": ("GET", "/users/@me/guilds"),
        "get_guild_member_info": ("GET", "/guilds/{guild_id}/members/{user_id}"),
        "get_guild_member_list": ("GET", "/guilds/{guild_id}/members"),
        "get_channel_info": ("GET", "/channels/{channel_id}"),
        "get_channel_list": ("GET", "/guilds/{guild_id}/channels"),
        "set_channel_name": ("PATCH", "/channels/{channel_id}"),
        "leave_channel": ("DELETE", "/channels/{channel_id}"),
        "get_channel_member_permissions": ("GET", "/channels/{channel_id}/members/{user_id}/permissions"),
    }

    # ==================== Send DSL ====================

    class Send(sdk.BaseAdapter.Send):

        def __init__(self, adapter, target_type=None, target_id=None, account_id=None, rules=None):
            super().__init__(adapter, target_type, target_id, account_id, rules)
            self._keyboard = None

        def Keyboard(self, keyboard: dict):
            """
            附加键盘按钮（自动将消息置为 markdown 类型并附带 bot_appid）

            :param keyboard: 键盘结构（模板键盘 {"id": ...} 或内联键盘 {"content": {"rows": [...]}}）
            :return: Send 实例，支持链式调用

            :example:
            >>> await qqbot.Send.To("group", group_openid).Keyboard(keyboard).Text("请选择")
            """
            self._keyboard = keyboard
            return self

        def Markdown(
            self,
            content: Optional[str] = None,
            *,
            template_id: Optional[int] = None,
            custom_template_id: Optional[str] = None,
            kv: Optional[list] = None,
            **kwargs,
        ):
            """
            发送 Markdown 消息（原生文本或模板）

            :param content: Markdown 原文（与模板二选一）
            :param template_id: 模板ID（数字）
            :param custom_template_id: 自定义模板ID（字符串）
            :param kv: 模板参数列表
            :return: asyncio.Task

            :example:
            >>> await qqbot.Send.To("group", gid).Markdown("# 标题\\n- 列表")
            >>> await qqbot.Send.To("user", uid).Markdown(template_id=1, kv=[{"key": "title", "value": "通知"}])
            """
            data: Dict[str, Any] = {}
            if custom_template_id is not None:
                data["custom_template_id"] = custom_template_id
                data["kv"] = kv or []
            elif template_id is not None:
                data["template_id"] = template_id
                data["kv"] = kv or []
            else:
                data["content"] = content or ""
            return self.Raw_ob12([{"type": "markdown", "data": data}], **kwargs)

        def Ark(self, template_id: int, kv: Optional[list] = None, **kwargs):
            """
            发送 Ark 模板消息

            :param template_id: Ark 模板ID
            :param kv: 模板键值参数
            :return: asyncio.Task

            :example:
            >>> await qqbot.Send.To("user", openid).Ark(1, [{"key": "title", "value": "标题"}])
            """
            return self.Raw_ob12(
                [{"type": "ark", "data": {"template_id": template_id, "kv": kv or []}}], **kwargs
            )

        def Embed(self, embed_data: dict, **kwargs):
            """
            发送 Embed 消息（仅频道/频道私信有效）

            :param embed_data: Embed 结构 {"title": ..., "prompt": ..., "fields": [...]}
            :return: asyncio.Task

            :example:
            >>> await qqbot.Send.To("channel", cid).Embed({"title": "标题", "content": "内容"})
            """
            return self.Raw_ob12([{"type": "embed", "data": embed_data}], **kwargs)

        def Stream(
            self,
            content: str,
            *,
            content_type: str = "text",
            msg_id: Optional[str] = None,
            event_id: Optional[str] = None,
            stream_msg_id: Optional[str] = None,
            index: int = 0,
            input_state: int = 10,
            **kwargs,
        ):
            """
            单聊流式消息（一次性发送完整内容；仅 user 目标支持）

            :param content: 文本内容
            :param content_type: "text" 或 "markdown"
            :param msg_id: 被动回复的消息ID（可选）
            :param event_id: 被动回复的事件ID（可选）
            :param stream_msg_id: 续传流ID（分片追加时传上次响应的 id）
            :param index: 分片序号（从0开始）
            :param input_state: 1=生成中 10=结束（默认一次性完成）
            :return: asyncio.Task

            :example:
            >>> await qqbot.Send.To("user", openid).Stream("回答内容")
            """
            async def _do():
                target_id = self._target_id
                account_id = self._account_id
                self._reset_modifiers()
                return await self._adapter.stream_message(
                    target_id,
                    content,
                    content_type=content_type,
                    msg_id=msg_id,
                    event_id=event_id,
                    stream_msg_id=stream_msg_id,
                    index=index,
                    input_state=input_state,
                    account_id=account_id,
                )

            return asyncio.create_task(_do())

        def _reset_modifiers(self):
            self._at_user_ids.clear()
            self._reply_message_id = None
            self._at_all = False
            self._keyboard = None

        def Raw_ob12(self, message, **kwargs):
            """
            发送 OneBot12 消息段（QQ官方协议实现）

            支持段：text / mention(at) / mention_all / reply / face / image / voice / video / file / markdown / ark / embed
            """
            async def _do():
                try:
                    segments = self._apply_modifiers(message)
                    ctx = self.send_context
                    return await self._adapter._send_segments(
                        segments,
                        ctx.get("target_type"),
                        ctx.get("target_id"),
                        account_id=ctx.get("account_id"),
                        keyboard=self._keyboard,
                        **kwargs,
                    )
                finally:
                    self._reset_modifiers()

            return asyncio.create_task(_do())

    # ==================== Request DSL ====================

    class Request(sdk.BaseAdapter.Request):
        """请求操作（GROUP_JOIN_REQUEST 入群申请的同意/拒绝）"""

        async def _do_accept(self, **kwargs) -> dict:
            return await self._adapter._handle_group_join_request(self._request_id, True, **kwargs)

        async def _do_reject(self, **kwargs) -> dict:
            return await self._adapter._handle_group_join_request(self._request_id, False, **kwargs)

    # ==================== Api DSL ====================

    class Api(sdk.BaseAdapter.Api):
        """OneBot12 标准 API 动作（映射到 QQ官方 API 并标准化 data 字段）"""

        @property
        def _ad(self) -> "QQBotAdapter":
            return self._adapter

        async def get_self_info(self) -> dict:
            r = await self._ad._request("GET", "/users/@me", account_id=self._account_id)
            if r.get("status") != "ok":
                return r
            u = r.get("data") or {}
            r["data"] = {
                "user_id": str(u.get("id", "")),
                "user_name": u.get("username", ""),
                "user_displayname": u.get("nickname") or u.get("username", ""),
            }
            return r

        async def get_guild_info(self, guild_id: str) -> dict:
            r = await self._ad._request("GET", f"/guilds/{guild_id}", account_id=self._account_id)
            if r.get("status") != "ok":
                return r
            g = r.get("data") or {}
            r["data"] = {"guild_id": str(g.get("id", "")), "guild_name": g.get("name", "")}
            return r

        async def get_guild_list(self) -> dict:
            r = await self._ad._request("GET", "/users/@me/guilds", params={"after": "0"}, account_id=self._account_id)
            if r.get("status") != "ok":
                return r
            r["data"] = [
                {"guild_id": str(g.get("id", "")), "guild_name": g.get("name", "")}
                for g in (r.get("data") or [])
                if isinstance(g, dict)
            ]
            return r

        async def get_guild_member_info(self, guild_id: str, user_id: str) -> dict:
            r = await self._ad._request(
                "GET", f"/guilds/{guild_id}/members/{user_id}", account_id=self._account_id
            )
            if r.get("status") != "ok":
                return r
            m = r.get("data") or {}
            user = m.get("user", {}) or {}
            r["data"] = {
                "user_id": str(user.get("id", "")),
                "user_name": user.get("username", ""),
                "user_displayname": m.get("nick") or user.get("username", ""),
            }
            return r

        async def get_guild_member_list(self, guild_id: str) -> dict:
            members: List[dict] = []
            after = "0"
            raw = None
            for _ in range(50):
                r = await self._ad._request(
                    "GET",
                    f"/guilds/{guild_id}/members",
                    params={"after": after, "limit": "100"},
                    account_id=self._account_id,
                )
                if r.get("status") != "ok":
                    if not members:
                        return r
                    break
                raw = r
                page = r.get("data") or []
                if not isinstance(page, list) or not page:
                    break
                for m in page:
                    user = (m or {}).get("user", {}) or {}
                    members.append({
                        "user_id": str(user.get("id", "")),
                        "user_name": user.get("username", ""),
                        "user_displayname": (m or {}).get("nick") or user.get("username", ""),
                    })
                if len(page) < 100:
                    break
                after = str((page[-1] or {}).get("user", {}).get("id", ""))
                if not after or after == "0":
                    break
            if raw is None:
                return self._ad.make_response(data=members)
            raw["data"] = members
            return raw

        async def get_channel_info(self, guild_id: str, channel_id: str) -> dict:
            r = await self._ad._request("GET", f"/channels/{channel_id}", account_id=self._account_id)
            if r.get("status") != "ok":
                return r
            c = r.get("data") or {}
            r["data"] = {"channel_id": str(c.get("id", "")), "channel_name": c.get("name", "")}
            return r

        async def get_channel_list(self, guild_id: str, *, joined_only: bool = False) -> dict:
            r = await self._ad._request("GET", f"/guilds/{guild_id}/channels", account_id=self._account_id)
            if r.get("status") != "ok":
                return r
            r["data"] = [
                {"channel_id": str(c.get("id", "")), "channel_name": c.get("name", "")}
                for c in (r.get("data") or [])
                if isinstance(c, dict)
            ]
            return r

        async def set_channel_name(self, guild_id: str, channel_id: str, channel_name: str) -> dict:
            return await self._ad._request(
                "PATCH", f"/channels/{channel_id}", json_body={"name": channel_name}, account_id=self._account_id
            )

        async def get_group_info(self, group_id: str) -> dict:
            r = await self._ad._request("GET", f"/v2/groups/{group_id}/info", account_id=self._account_id)
            if r.get("status") != "ok":
                return r
            g = r.get("data") or {}
            r["data"] = {"group_id": str(g.get("group_openid", group_id)), "group_name": g.get("group_name", "")}
            return r

        async def get_group_member_info(self, group_id: str, user_id: str) -> dict:
            r = await self._ad._request(
                "GET", f"/v2/groups/{group_id}/members/{user_id}", account_id=self._account_id
            )
            if r.get("status") != "ok":
                return r
            m = r.get("data") or {}
            r["data"] = {
                "user_id": str(m.get("member_openid", user_id)),
                "user_name": m.get("nickname") or m.get("username", ""),
                "user_displayname": m.get("nickname") or m.get("username", ""),
            }
            return r

        async def get_group_member_list(self, group_id: str) -> dict:
            members: List[dict] = []
            cursor = ""
            raw = None
            for _ in range(100):
                params = {"cursor": cursor} if cursor else {}
                r = await self._ad._request(
                    "GET", f"/v2/groups/{group_id}/members", params=params or None, account_id=self._account_id
                )
                if r.get("status") != "ok":
                    if not members:
                        return r
                    break
                raw = r
                page = (r.get("data") or {})
                items = page.get("members", []) if isinstance(page, dict) else (page or [])
                for m in items or []:
                    members.append({
                        "user_id": str((m or {}).get("member_openid", "")),
                        "user_name": (m or {}).get("nickname", ""),
                        "user_displayname": (m or {}).get("nickname", ""),
                    })
                next_cursor = page.get("next_cursor", "") if isinstance(page, dict) else ""
                if not items or not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
            if raw is None:
                return self._ad.make_response(data=members)
            raw["data"] = members
            return raw

        async def delete_message(self, message_id: str) -> dict:
            return await self._ad._delete_message_by_id(str(message_id), account_id=self._account_id)

        async def get_status(self) -> dict:
            ad = self._ad
            bots = []
            for name, rt in ad.iter_runtimes():
                bots.append({
                    "self": {"platform": ad.platform, "user_id": rt.bot_id, "account_id": name},
                    "online": rt.online,
                })
            return ad.make_response(data={"good": any(b["online"] for b in bots), "bots": bots})

        async def get_version(self) -> dict:
            from . import __version__

            return self._ad.make_response(
                data={"impl": "ErisPulse-QQBotAdapter", "version": __version__, "onebot_version": "12"}
            )

        async def get_supported_actions(self) -> dict:
            actions = set(self._ad._OB12_ROUTES)
            actions.update([
                "delete_message", "get_status", "get_version", "get_supported_actions",
                "get_self_info", "get_guild_info", "get_guild_list", "get_guild_member_info",
                "get_guild_member_list", "get_channel_info", "get_channel_list", "set_channel_name",
                "get_group_info", "get_group_member_info", "get_group_member_list",
            ])
            return self._ad.make_response(data=sorted(actions))

        async def get_latest_events(self, limit: int = 0, timeout: int = 0) -> dict:
            return self._ad.make_error(retcode=10002, message="QQBot 适配器不缓存事件历史")

    # ==================== 生命周期 ====================

    def _get_config_key(self) -> str:
        return "QQBot_Adapter"

    def __init__(self, sdk_instance=None):
        super().__init__(sdk_instance)
        self.bot_id = ""
        self._bot_name = ""
        self._runtimes: Dict[str, _AccountRuntime] = {}
        self._account_tasks: Dict[str, asyncio.Task] = {}
        self._message_targets: Dict[str, Tuple[str, str]] = {}
        self._pending_msg_ids: Dict[str, str] = {}
        self._pending_requests: Dict[str, dict] = {}
        self._bot_group_openids: Dict[str, str] = {}
        self._sandbox_warned = False

        converter = QQBotConverter(
            bot_id_getter=lambda: self.bot_id,
            group_openids=self._bot_group_openids,
            bot_name_getter=lambda: self._bot_name,
        )
        converter._logger = self._get_logger()
        self.convert = converter.convert

        self._check_framework_version()
        self._get_logger().info(f"QQBotAdapter v{__version__} 已加载")

    @staticmethod
    def _parse_version(version_str: str) -> tuple:
        """解析版本号为可比较的三元组（忽略 dev/预发布后缀，如 2.8.0-dev.3 → (2, 8, 0)）"""
        parts = []
        for piece in str(version_str).split("."):
            digits = "".join(ch for ch in piece if ch.isdigit())
            parts.append(int(digits) if digits else 0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def _check_framework_version(self):
        """软依赖检测：框架版本过低时打警告（不阻断加载）"""
        try:
            from importlib.metadata import version as _pkg_version

            raw = _pkg_version("ErisPulse")
        except Exception:
            return
        try:
            if self._parse_version(raw) < MIN_FRAMEWORK_VERSION:
                self._get_logger().warning(
                    f"当前 ErisPulse 版本 {raw} 过低：QQBotAdapter v5 需要 >= "
                    f"{'.'.join(map(str, MIN_FRAMEWORK_VERSION))}"
                    "（BaseConverter / Api/Request DSL / spawn_background 等特性），"
                    "部分功能可能不可用，建议升级框架"
                )
        except Exception:
            pass

        self._migrate_legacy_config()

    def _migrate_legacy_config(self):
        """将 v3 及以前的扁平配置（[QQBot_Adapter] appid=...）迁移到 accounts 结构"""
        try:
            from ErisPulse.Core import config as config_mgr

            key = self._get_config_key()
            data = config_mgr.getConfig(key)
            if not isinstance(data, dict):
                return
            appid = data.get("appid")
            secret = data.get("secret")
            if not appid or not secret:
                return
            accounts = data.get("accounts")
            if isinstance(accounts, dict) and accounts:
                # 已有真实账户配置时不迁移
                has_real = any(
                    isinstance(a, dict) and a.get("appid") not in ("", "YOUR_APPID", None)
                    for a in accounts.values()
                )
                if has_real:
                    return
            new_account = {"appid": appid, "secret": secret, "mode": "websocket", "enabled": True}
            if data.get("sandbox"):
                new_account["sandbox"] = True
            data["accounts"] = {"default": new_account}
            config_mgr.setConfig(key, data)
            self.logger.info("已将旧版扁平配置迁移到 accounts.default")
        except Exception as e:
            self.logger.debug(f"旧配置迁移检查跳过: {e}")

    async def start(self):
        enabled = self.enabled_accounts
        usable = {}
        for name, cfg in enabled.items():
            if not cfg.appid or not cfg.secret:
                self.logger.warning(f"账户 {name} 缺少 appid/secret，已跳过")
                continue
            usable[name] = cfg
        if not usable:
            self.logger.warning("没有找到可用的账户配置（需要在 QQBot_Adapter.accounts 下填写 appid/secret）")
            return

        for name, cfg in usable.items():
            rt = self._runtimes.get(name)
            if rt is None:
                rt = _AccountRuntime(name, cfg)
                self._runtimes[name] = rt
            rt.config = cfg

        for name in usable:
            task = self._spawn(self._run_account(name))
            self._account_tasks[name] = task

        self.logger.info(f"QQBot 适配器已启动，共 {len(usable)} 个账户")

    async def shutdown(self):
        for rt in list(self._runtimes.values()):
            if rt.bot_id:
                try:
                    await self.emit_meta("disconnect", rt.bot_id)
                except Exception:
                    pass

        for task in self._account_tasks.values():
            task.cancel()
        if self._account_tasks:
            await asyncio.gather(*self._account_tasks.values(), return_exceptions=True)
        self._account_tasks.clear()

        for rt in self._runtimes.values():
            if rt.ws is not None:
                try:
                    await rt.ws.close()
                except Exception:
                    pass
                rt.ws = None
            if rt.webhook is not None:
                try:
                    rt.webhook.stop()
                except Exception:
                    pass
                rt.webhook = None

        self.logger.info("QQBot 适配器已关闭")

    def _spawn(self, coro) -> asyncio.Task:
        if spawn_background is not None:
            return spawn_background(coro)
        return asyncio.create_task(coro)

    async def _run_account(self, name: str):
        rt = self._runtimes[name]
        cfg = rt.config
        if cfg.sandbox and not self._sandbox_warned:
            self._sandbox_warned = True
            self.logger.warning(f"账户 {name}: sandbox 已废弃，官方已统一使用 {DEFAULT_API_BASE_URL}")

        try:
            await self._fetch_self_info(rt)
        except Exception as e:
            self.logger.warning(f"账户 {name} 获取机器人信息失败: {e}")

        if cfg.mode == "webhook":
            await self._run_webhook_account(name, rt)
        else:
            await self._run_ws_account(name, rt)

    async def _fetch_self_info(self, rt: _AccountRuntime):
        r = await self._request("GET", "/users/@me", account_id=rt.name)
        if r.get("status") == "ok" and isinstance(r.get("data"), dict):
            u = r["data"]
            rt.bot_id = str(u.get("id", ""))
            rt.user_name = u.get("username", "")
            if not self.bot_id:
                self.bot_id = rt.bot_id
            if not self._bot_name:
                self._bot_name = rt.user_name
            if hasattr(rt.config, "bot_id"):
                try:
                    rt.config.bot_id = rt.bot_id
                except Exception:
                    pass
            self.logger.info(f"账户 {rt.name} 机器人信息: {rt.bot_id} ({rt.user_name})")

    async def _run_ws_account(self, name: str, rt: _AccountRuntime):
        ws = QQBotWebSocket(self, name, rt)
        rt.ws = ws
        try:
            await ws.run()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"账户 {name} WebSocket 异常退出: {e}")
        finally:
            rt.ws = None

    async def _run_webhook_account(self, name: str, rt: _AccountRuntime):
        from .Webhook import QQBotWebhook

        hook = QQBotWebhook(self, name, rt)
        rt.webhook = hook
        try:
            await hook.start()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"账户 {name} Webhook 异常退出: {e}")
        finally:
            rt.webhook = None

    async def _on_account_ready(self, rt: _AccountRuntime):
        """READY 后：注册 Bot 状态 + 开始 meta 心跳"""
        if not rt.bot_id:
            return
        if not self.bot_id:
            self.bot_id = rt.bot_id
        try:
            await self.emit_meta("connect", rt.bot_id, user_name=rt.user_name)
        except Exception as e:
            self.logger.debug(f"发送 connect meta 失败: {e}")

    def iter_runtimes(self):
        return self._runtimes.items()

    # ==================== Token 管理 ====================

    def _get_runtime(self, name: str, cfg) -> _AccountRuntime:
        rt = self._runtimes.get(name)
        if rt is None:
            rt = _AccountRuntime(name, cfg)
            self._runtimes[name] = rt
        return rt

    async def _ensure_token(self, rt: _AccountRuntime) -> str:
        if rt.token and _time.time() < rt.token_expires - TOKEN_REFRESH_BUFFER:
            return rt.token
        await self._refresh_token(rt)
        return rt.token

    async def _refresh_token(self, rt: _AccountRuntime):
        cfg = rt.config
        url = cfg.access_token_url or DEFAULT_ACCESS_TOKEN_URL
        last_exc: Optional[Exception] = None
        for attempt in range(TOKEN_RETRY_TIMES):
            try:
                resp = await client.post(
                    url,
                    json={"appId": cfg.appid, "clientSecret": cfg.secret},
                    headers={"Content-Type": "application/json", "User-Agent": "QQBot/1.0"},
                    timeout=10,
                )
                data = await resp.json()
                token = (data or {}).get("access_token", "")
                if not token:
                    raise ValueError(f"响应缺少 access_token: {(data or {}).get('message', data)}")
                rt.token = token
                rt.token_expires = _time.time() + int((data or {}).get("expires_in", 7200))
                self.logger.debug(f"账户 {rt.name} Access Token 已获取/刷新")
                return
            except Exception as e:
                last_exc = e
                await asyncio.sleep(0.5 * (attempt + 1))
        self.logger.error(f"账户 {rt.name} 获取 Access Token 失败: {last_exc}")
        raise last_exc  # type: ignore[misc]

    # ==================== HTTP 核心 ====================

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: Optional[dict] = None,
        account_id: Optional[str] = None,
    ) -> dict:
        try:
            name, cfg = self._resolve_account(account_id)
        except ValueError as e:
            return self.make_error(retcode=10003, message=str(e))
        rt = self._get_runtime(name, cfg)
        return await self._http(
            method,
            f"{(cfg.api_base_url or DEFAULT_API_BASE_URL).rstrip('/')}{path}",
            json_body=json_body,
            params=params,
            rt=rt,
            cfg=cfg,
        )

    async def _http(
        self,
        method: str,
        url: str,
        *,
        json_body: Any = None,
        params: Optional[dict] = None,
        data: Any = None,
        files: Optional[dict] = None,
        rt: Optional[_AccountRuntime] = None,
        cfg: Any = None,
    ) -> dict:
        if rt is None or cfg is None:
            name, cfg = self._resolve_account(None)
            rt = self._get_runtime(name, cfg)
        try:
            token = await self._ensure_token(rt)
        except Exception as e:
            return self.make_error(retcode=33000, message=f"获取 Access Token 失败: {e}")

        headers = {
            "Authorization": f"QQBot {token}",
            "X-Union-Appid": cfg.appid,
            "Content-Type": "application/json",
        }
        try:
            resp = await client.request(
                method.upper(),
                url,
                params={k: str(v) for k, v in (params or {}).items()},
                json=json_body,
                data=data,
                files=files,
                headers=headers,
                timeout=30,
            )
            try:
                raw = await resp.json()
            except Exception:
                raw = None
            return self._normalize_api_result(raw, resp.status)
        except ClientTimeoutError:
            self.logger.error(f"QQBot API 请求超时: {method} {url}")
            return self.make_error(retcode=32000, message="请求超时")
        except ClientConnectionError as e:
            self.logger.error(f"QQBot API 网络连接失败: {e}")
            return self.make_error(retcode=33000, message=f"网络连接失败: {e}")
        except ClientError as e:
            self.logger.error(f"QQBot API 调用失败: {e}")
            return self.make_error(retcode=33000, message=f"API调用失败: {e}")
        except Exception as e:
            self.logger.error(f"QQBot API 调用异常: {e}")
            return self.make_error(retcode=33000, message=f"API调用异常: {e}")

    def _normalize_api_result(self, raw: Any, status_code: int = 0) -> dict:
        if raw is None:
            if status_code and 200 <= status_code < 300:
                return self.make_response(data=None)
            return self.make_error(retcode=status_code or 34000, message=f"HTTP {status_code or '响应解析失败'}")

        if not isinstance(raw, dict):
            return self.make_response(data=raw, raw=raw)

        code = raw.get("code", 0)
        if 200 <= (status_code or 200) < 300 and code in (0, None):
            msg_id = raw.get("id", "")
            return self.make_response(
                data=raw.get("data", raw),
                message_id=str(msg_id) if msg_id else "",
                raw=raw,
            )
        # 官方将部分提示码视为警告（如 304023/304024）
        if code in (304023, 304024):
            return self.make_response(data=raw.get("data", raw), raw=raw)
        return self.make_error(
            retcode=code or status_code or 34000,
            message=raw.get("message", "Unknown QQBot API error"),
            raw=raw,
        )

    async def call_api(self, endpoint: str, **params) -> dict:
        """
        调用 QQ API

        - endpoint 以 "/" 开头：直接作为平台 REST 路径调用（默认 POST）
        - endpoint 为 OneBot12 标准动作名：按路由表映射到平台端点
        - kwargs 中的 account_id 用于多账户选择（Send/Request/Api DSL 自动注入）
        - kwargs 中的 _method 可覆盖 HTTP 方法
        """
        account_id = params.pop("account_id", None)
        method = str(params.pop("_method", "POST") or "POST").upper()

        if not isinstance(endpoint, str) or not endpoint:
            return self.make_error(retcode=10001, message="endpoint 不能为空")

        if not endpoint.startswith("/"):
            route = self._OB12_ROUTES.get(endpoint)
            if route is None:
                return self.make_error(retcode=10002, message=f"不支持的动作: {endpoint}")
            method, template = route
            path_keys = set(re.findall(r"\{(\w+)\}", template))
            path_params = {k: params.pop(k) for k in list(params) if k in path_keys}
            missing = path_keys - path_params.keys()
            if missing:
                return self.make_error(retcode=10001, message=f"缺少路径参数: {', '.join(sorted(missing))}")
            endpoint = template.format(**path_params)

        if method == "GET":
            return await self._request("GET", endpoint, params=params or None, account_id=account_id)
        return await self._request(method, endpoint, json_body=params or None, account_id=account_id)

    # ==================== 消息发送核心 ====================

    async def _send_segments(
        self,
        segments: List[dict],
        target_type: Optional[str],
        target_id: Optional[str],
        *,
        account_id: Optional[str] = None,
        keyboard: Optional[dict] = None,
        **kwargs,
    ) -> dict:
        if not target_type or not target_id:
            return self.make_error(retcode=10003, message="无法确定发送目标")

        try:
            name, cfg = self._resolve_account(account_id)
        except ValueError as e:
            return self.make_error(retcode=10003, message=str(e))

        is_v2 = target_type in ("user", "group")
        is_channel = target_type in ("channel", "dms")

        text_parts: List[str] = []
        media_ref: Any = None
        media_seg_type = ""
        file_name: Optional[str] = kwargs.get("file_name")
        markdown_data: Optional[dict] = None
        ark_data: Optional[dict] = None
        embed_data: Optional[dict] = None
        msg_id = str(kwargs.get("msg_id") or "")
        event_id = str(kwargs.get("event_id") or "")
        has_reply = False

        for seg in segments:
            if not isinstance(seg, dict):
                continue
            seg_type = seg.get("type")
            data = seg.get("data", {}) or {}

            if seg_type == "text":
                text_parts.append(str(data.get("text", "")))
            elif seg_type in ("mention", "at"):
                uid = str(data.get("user_id", ""))
                if uid:
                    text_parts.append(f"<@{uid}>" if is_channel else f'<qqbot-at-user id="{uid}" />')
            elif seg_type == "mention_all":
                text_parts.append("@everyone" if is_channel else "<qqbot-at-everyone />")
            elif seg_type == "face":
                if is_channel:
                    text_parts.append(f"<emoji:{data.get('id', '')}>")
            elif seg_type == "reply":
                has_reply = True
                if data.get("event_id"):
                    event_id = str(data["event_id"])
                elif data.get("message_id"):
                    msg_id = str(data["message_id"])
            elif seg_type in SEGMENT_FILE_TYPES:
                if media_ref:
                    self.logger.warning("QQBot 单条消息仅支持一个媒体段，多余媒体已忽略")
                    continue
                media_seg_type = seg_type
                media_ref = data.get("file") or data.get("url") or ""
                file_name = data.get("filename") or file_name
            elif seg_type == "markdown":
                markdown_data = data
            elif seg_type == "ark":
                ark_data = data
            elif seg_type == "embed":
                embed_data = data
            else:
                self.logger.debug(f"忽略不支持的消息段: {seg_type}")

        # 被动回复兜底：使用最近一次收到的消息
        if not msg_id and not event_id and target_id:
            msg_id = self._pending_msg_ids.get(f"{target_type}:{target_id}", "")

        content = "".join(text_parts).strip()

        if target_type == "user":
            endpoint = f"/v2/users/{target_id}/messages"
        elif target_type == "group":
            endpoint = f"/v2/groups/{target_id}/messages"
        elif target_type == "channel":
            endpoint = f"/channels/{target_id}/messages"
        elif target_type == "dms":
            endpoint = f"/dms/{target_id}/messages"
        else:
            return self.make_error(retcode=10003, message=f"不支持的目标类型: {target_type}")

        # msg_type 判定
        msg_type = 0
        if markdown_data is not None or keyboard is not None:
            msg_type = 2
        if ark_data is not None:
            msg_type = 3
        if embed_data is not None and is_channel:
            msg_type = 4
        if media_ref and is_v2:
            msg_type = 7

        params: Dict[str, Any] = {"msg_type": msg_type}

        if msg_type in (0, 7):
            params["content"] = content or " "
        elif msg_type == 2:
            if markdown_data is not None and (
                markdown_data.get("template_id") is not None or markdown_data.get("custom_template_id") is not None
            ):
                md: Dict[str, Any] = {"kv": markdown_data.get("kv", [])}
                if markdown_data.get("custom_template_id") is not None:
                    md["custom_template_id"] = markdown_data["custom_template_id"]
                else:
                    md["template_id"] = markdown_data["template_id"]
                params["markdown"] = md
            else:
                md_content = (markdown_data or {}).get("content", "") or content
                params["markdown"] = {"content": md_content or " "}
        elif msg_type == 3:
            params["ark"] = {
                "template_id": (ark_data or {}).get("template_id", 0),
                "kv": (ark_data or {}).get("kv", []),
            }
        elif msg_type == 4:
            params["embed"] = embed_data

        # 媒体：群/私聊走 v2 富媒体上传；频道走 multipart
        if media_ref:
            if event_id:
                # 官方限制：event_id 不能与富媒体混发
                self.logger.debug("富媒体消息不支持 event_id 被动回复，已忽略 event_id")
                event_id = ""
            if is_v2:
                file_type = SEGMENT_FILE_TYPES.get(media_seg_type, 1)
                file_info = await self._upload_media(
                    media_ref,
                    target_type,
                    target_id,
                    file_type,
                    account_id=name,
                    file_name=file_name,
                )
                if not file_info:
                    return self.make_error(retcode=34100, message="媒体上传失败")
                params["media"] = {"file_info": file_info}
            elif is_channel:
                if media_seg_type != "image":
                    return self.make_error(retcode=10003, message="频道消息仅支持图片媒体（file_image）")
                msg_seq = int(kwargs.get("msg_seq") or random.randint(1, 999999))
                form: Dict[str, Any] = {"content": content}
                if msg_id:
                    form["msg_id"] = msg_id
                    form["msg_seq"] = str(msg_seq)
                files = None
                if isinstance(media_ref, str) and media_ref.startswith(("http://", "https://")):
                    form["image"] = media_ref
                else:
                    image_bytes = self._read_media_bytes(media_ref)
                    if image_bytes is None:
                        return self.make_error(retcode=32100, message=f"无法读取图片: {media_ref!r}")
                    fname = file_name or "image.png"
                    files = {"file_image": (fname, image_bytes, "application/octet-stream")}
                base = (cfg.api_base_url or DEFAULT_API_BASE_URL).rstrip("/")
                resp_result = await self._http(
                    "POST",
                    f"{base}{endpoint}",
                    data=form,
                    files=files,
                    rt=self._get_runtime(name, cfg),
                    cfg=cfg,
                )
                self._register_outbound_message(resp_result, target_type, target_id)
                return resp_result

        # 被动回复参数
        if msg_id:
            params["msg_id"] = msg_id
            params.setdefault("msg_seq", int(kwargs.get("msg_seq") or random.randint(1, 999999)))
            if has_reply and is_channel:
                params["message_reference"] = {"message_id": msg_id}
        if event_id:
            params["event_id"] = event_id
            params.setdefault("msg_seq", int(kwargs.get("msg_seq") or random.randint(1, 999999)))

        if keyboard is not None:
            params["keyboard"] = keyboard
            params["bot_appid"] = cfg.appid

        result = await self._request("POST", endpoint, json_body=params, account_id=name)
        self._register_outbound_message(result, target_type, target_id)
        return result

    def _read_media_bytes(self, ref: Any) -> Optional[bytes]:
        if isinstance(ref, (bytes, bytearray)):
            return bytes(ref)
        if isinstance(ref, str) and os.path.isfile(ref):
            try:
                with open(ref, "rb") as f:
                    return f.read()
            except Exception as e:
                self.logger.error(f"读取本地文件失败: {e}")
        return None

    def _register_outbound_message(self, result: dict, target_type: str, target_id: str):
        if result.get("status") == "ok" and result.get("message_id"):
            self._message_targets[result["message_id"]] = (target_type, target_id)
            self._trim_dict(self._message_targets)

    async def _delete_message_by_id(self, message_id: str, account_id: Optional[str] = None) -> dict:
        target = self._message_targets.get(message_id)
        if not target:
            return self.make_error(retcode=34001, message=f"未找到消息 {message_id} 的目标上下文，无法撤回")
        target_type, target_id = target
        if target_type == "channel":
            return await self._request(
                "DELETE", f"/channels/{target_id}/messages/{message_id}",
                params={"hidetip": "false"}, account_id=account_id,
            )
        if target_type == "dms":
            return await self._request(
                "DELETE", f"/dms/{target_id}/messages/{message_id}",
                params={"hidetip": "false"}, account_id=account_id,
            )
        if target_type == "group":
            return await self._request(
                "DELETE", f"/v2/groups/{target_id}/messages/{message_id}", account_id=account_id
            )
        return await self._request(
            "DELETE", f"/v2/users/{target_id}/messages/{message_id}", account_id=account_id
        )

    # ==================== 流式消息 ====================

    async def stream_message(
        self,
        user_id: str,
        content: str,
        *,
        content_type: str = "text",
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
        stream_msg_id: Optional[str] = None,
        index: int = 0,
        input_state: int = 10,
        msg_seq: Optional[int] = None,
        is_wakeup: bool = False,
        account_id: Optional[str] = None,
    ) -> dict:
        """
        单聊流式消息（/v2/users/{id}/stream_messages）

        多轮追加：首次调用不传 stream_msg_id，从响应 data.id 取得流ID；
        后续调用传 stream_msg_id=流ID、index 递增；结束时 input_state=10。
        """
        if not msg_id and not event_id and user_id:
            msg_id = self._pending_msg_ids.get(f"user:{user_id}", "")
        payload: Dict[str, Any] = {
            "content": content,
            "content_type": content_type,
            "index": index,
            "input_state": input_state,
            "msg_seq": msg_seq or random.randint(1, 999999),
            "is_wakeup": is_wakeup,
        }
        if stream_msg_id:
            payload["stream_msg_id"] = stream_msg_id
        if msg_id:
            payload["msg_id"] = msg_id
        if event_id:
            payload["event_id"] = event_id
        return await self._request("POST", f"/v2/users/{user_id}/stream_messages", json_body=payload, account_id=account_id)

    # ==================== 富媒体上传 ====================

    @staticmethod
    def _infer_file_type(ref: Any) -> int:
        ext = ""
        if isinstance(ref, str):
            path_part = ref.split("?")[0] if ref.startswith(("http://", "https://")) else ref
            ext = os.path.splitext(path_part)[1].lower()
        return _EXTENSION_FILE_TYPES.get(ext, 4)

    async def _upload_media(
        self,
        file: Any,
        target_type: str,
        target_id: str,
        file_type: Optional[int] = None,
        *,
        account_id: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> Optional[str]:
        """上传富媒体，返回 file_info；支持 URL / 本地路径 / 二进制，大文件自动分片"""
        ft = file_type or self._infer_file_type(file_name or file)
        data: Optional[bytes] = None
        payload: Dict[str, Any] = {"file_type": ft, "srv_send_msg": False}

        if isinstance(file, str) and file.startswith(("http://", "https://")):
            payload["url"] = file
        else:
            data = self._read_media_bytes(file)
            if data is None:
                self.logger.error(f"无法读取媒体文件: {file!r}")
                return None
            fname = file_name or (os.path.basename(str(file)) if isinstance(file, str) else DEFAULT_FILE_NAMES[ft])
            if len(data) > CHUNK_THRESHOLD:
                return await self._upload_media_chunked(
                    data, target_type, target_id, ft, account_id=account_id, file_name=fname
                )
            payload["file_data"] = base64.b64encode(data).decode("utf-8")
            payload["file_name"] = fname

        payload.setdefault("file_name", DEFAULT_FILE_NAMES[ft])

        if target_type == "user":
            endpoint = f"/v2/users/{target_id}/files"
        elif target_type == "group":
            endpoint = f"/v2/groups/{target_id}/files"
        else:
            self.logger.error(f"媒体上传仅支持 user/group 目标，收到: {target_type}")
            return None

        result = await self._request("POST", endpoint, json_body=payload, account_id=account_id)
        if result.get("status") != "ok":
            self.logger.error(f"上传媒体失败: {result.get('message')}")
            return None
        file_info = (result.get("data") or {}).get("file_info", "")
        if not file_info:
            self.logger.error("上传媒体响应缺少 file_info")
            return None
        return file_info

    async def _upload_media_chunked(
        self,
        data: bytes,
        target_type: str,
        target_id: str,
        file_type: int,
        *,
        account_id: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> Optional[str]:
        """大文件分片上传：upload_prepare → PUT 预签名分片 → upload_part_finish → 合并"""
        seg = "users" if target_type == "user" else "groups"
        fname = file_name or DEFAULT_FILE_NAMES[file_type]
        prepare_body = {
            "file_type": file_type,
            "file_size": len(data),
            "file_name": fname,
            "md5": hashlib.md5(data).hexdigest(),
            "sha1": hashlib.sha1(data).hexdigest(),
            "md5_10m": hashlib.md5(data[: 10 * 1024 * 1024]).hexdigest(),
        }
        result = await self._request(
            "POST", f"/v2/{seg}/{target_id}/upload_prepare", json_body=prepare_body, account_id=account_id
        )
        if result.get("status") != "ok":
            self.logger.error(f"分片上传 prepare 失败: {result.get('message')}")
            return None
        prep = result.get("data") or {}
        upload_id = prep.get("upload_id", "")
        parts = prep.get("parts", []) or []
        if not upload_id or not parts:
            self.logger.error("分片上传 prepare 响应缺少 upload_id/parts")
            return None

        for part in parts:
            index = int(part.get("index", 0))
            presigned = part.get("presigned_url", "")
            block_size = int(part.get("block_size", 0)) or (len(data) // len(parts))
            chunk = data[index * block_size: (index + 1) * block_size] if block_size else data
            try:
                await client.put(
                    presigned,
                    data=chunk,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=120,
                )
            except (ClientError, Exception) as e:
                self.logger.error(f"分片 PUT 失败 (index={index}): {e}")
                return None
            finish_result = await self._request(
                "POST",
                f"/v2/{seg}/{target_id}/upload_part_finish",
                json_body={
                    "upload_id": upload_id,
                    "part_index": index,
                    "block_size": len(chunk),
                    "md5": hashlib.md5(chunk).hexdigest(),
                },
                account_id=account_id,
            )
            if finish_result.get("status") != "ok":
                self.logger.error(f"分片 finish 失败 (index={index}): {finish_result.get('message')}")
                return None

        merge_result = await self._request(
            "POST",
            f"/v2/{seg}/{target_id}/files",
            json_body={"file_type": file_type, "srv_send_msg": False, "file_name": fname, "upload_id": upload_id},
            account_id=account_id,
        )
        if merge_result.get("status") != "ok":
            self.logger.error(f"分片合并失败: {merge_result.get('message')}")
            return None
        file_info = (merge_result.get("data") or {}).get("file_info", "")
        return file_info or None

    # ==================== 请求操作（入群申请） ====================

    def _register_request(self, event: dict, account_name: str):
        request_id = str(event.get("request_id", ""))
        if not request_id:
            return
        self._pending_requests[request_id] = {
            "group_openid": event.get("qqbot_group_openid") or event.get("group_id", ""),
            "member_openid": event.get("qqbot_member_openid") or event.get("user_id", ""),
            "account_name": account_name,
        }
        self._trim_dict(self._pending_requests)

    async def _handle_group_join_request(
        self,
        request_id: Optional[str],
        approve: bool,
        *,
        comment: str = "",
        reject_reason: str = "",
        account_id: Optional[str] = None,
        **kwargs,
    ) -> dict:
        if not request_id:
            return self.make_error(retcode=34001, message="缺少 request_id")
        ctx = self._pending_requests.get(request_id)
        if not ctx:
            return self.make_error(retcode=34001, message=f"请求 {request_id} 不存在或已过期")
        group_openid = ctx.get("group_openid", "")
        member_openid = ctx.get("member_openid", "")
        if not group_openid or not member_openid:
            return self.make_error(retcode=34003, message="请求上下文缺少 group_openid/member_openid")
        body: Dict[str, Any] = {"op": "approve" if approve else "decline", "join_request_id": request_id}
        reason = reject_reason or comment or kwargs.get("comment", "")
        if not approve and reason:
            body["reject_reason"] = reason
        if kwargs.get("add_to_member_blacklist"):
            body["add_to_member_blacklist"] = True
        return await self._request(
            "POST",
            f"/v2/groups/{group_openid}/approval_join_request/{member_openid}",
            json_body=body,
            account_id=account_id or ctx.get("account_name"),
        )

    # ==================== 事件分发 ====================

    async def _dispatch_event(self, payload: dict, raw_type: str, account_name: str = "") -> Optional[dict]:
        event = self.convert(payload, raw_type)
        if not event:
            return None
        self_info = event.setdefault("self", {})
        if account_name and "account_id" not in self_info:
            self_info["account_id"] = account_name

        event_type = event.get("type")
        if event_type == "message":
            self._store_event_msg_id(event)
            if event.get("detail_type") == "group":
                self._get_logger().debug(
                    f"[at检测] 群消息事件: raw_type={event.get('qqbot_raw_type')}, "
                    f"is_at={event.get('qqbot_is_at_message')}, "
                    f"self.user_id={self_info.get('user_id')!r}, "
                    f"mentions={[s.get('data', {}).get('user_id') for s in event.get('message', []) if s.get('type') == 'mention']}"
                )
        elif event_type == "request":
            self._register_request(event, account_name)
        if event_type == "unknown":
            self.logger.debug(f"收到未支持的事件: {event.get('qqbot_raw_type')}")

        await self.sdk.adapter.emit(event)
        return event

    def _store_event_msg_id(self, event: dict):
        detail_type = event.get("detail_type", "")
        msg_id = event.get("message_id", "")
        if not msg_id:
            return
        if detail_type == "group" and event.get("group_id"):
            self._pending_msg_ids[f"group:{event['group_id']}"] = msg_id
            self._message_targets[msg_id] = ("group", event["group_id"])
        elif detail_type == "private" and event.get("user_id"):
            self._pending_msg_ids[f"user:{event['user_id']}"] = msg_id
            if event.get("qqbot_raw_type") == "DIRECT_MESSAGE_CREATE" and event.get("qqbot_guild_id"):
                self._message_targets[msg_id] = ("dms", event["qqbot_guild_id"])
            else:
                self._message_targets[msg_id] = ("user", event["user_id"])
        elif detail_type == "channel" and event.get("channel_id"):
            self._pending_msg_ids[f"channel:{event['channel_id']}"] = msg_id
            self._message_targets[msg_id] = ("channel", event["channel_id"])
        self._trim_dict(self._pending_msg_ids)
        self._trim_dict(self._message_targets)

    @staticmethod
    def _trim_dict(d: dict, max_size: int = REGISTRY_MAX):
        while len(d) > max_size:
            try:
                d.pop(next(iter(d)))
            except StopIteration:
                break

    # ==================== 配置解析 ====================

    def _get_intents_value(self) -> int:
        raw = DEFAULT_INTENTS
        try:
            raw = self.cfg.intents
        except Exception:
            pass
        try:
            items = json.loads(raw) if isinstance(raw, str) else list(raw or [])
        except Exception:
            items = [0, 9, 12, 25, 26, 27]

        value = 0
        for item in items:
            if isinstance(item, str):
                name = item.strip().upper()
                if name in INTENT_BITS:
                    value |= 1 << INTENT_BITS[name]
                elif name.isdigit():
                    value |= 1 << int(name)
            elif isinstance(item, int) and 0 <= item <= 40:
                value |= 1 << item
        return value

    # ==================== 平台原生 API 方法族 ====================
    # ---------- 机器人 ----------

    async def get_me(self, account_id: Optional[str] = None) -> dict:
        """获取机器人信息（GET /users/@me）"""
        return await self._request("GET", "/users/@me", account_id=account_id)

    async def reply_interaction(self, interaction_id: str, code: int = 0, account_id: Optional[str] = None) -> dict:
        """回应按钮点击交互（PUT /interactions/{id}，code 0-5 为回执类型）"""
        return await self._request("PUT", f"/interactions/{interaction_id}", json_body={"code": code}, account_id=account_id)

    # ---------- 频道（Guild） ----------

    async def get_guilds(self, after: str = "", account_id: Optional[str] = None) -> dict:
        """获取自身加入的频道列表（单页，最多100）"""
        return await self._request("GET", "/users/@me/guilds", params={"after": after or "0"}, account_id=account_id)

    async def get_guild(self, guild_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/guilds/{guild_id}", account_id=account_id)

    async def mute_guild_all(self, guild_id: str, mute_seconds: str = "0", mute_end_timestamp: str = "", account_id: Optional[str] = None) -> dict:
        """全频道禁言/解除（mute_seconds="0" 解除）"""
        body = {"mute_seconds": str(mute_seconds)}
        if mute_end_timestamp:
            body["mute_end_timestamp"] = str(mute_end_timestamp)
        return await self._request("PUT", f"/guilds/{guild_id}/mute", json_body=body, account_id=account_id)

    async def get_guild_roles(self, guild_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/guilds/{guild_id}/roles", account_id=account_id)

    async def create_guild_role(self, guild_id: str, name: str = "", color: int = 0, hoist: int = 0, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "POST", f"/guilds/{guild_id}/roles", json_body={"name": name, "color": color, "hoist": hoist},
            account_id=account_id,
        )

    async def update_guild_role(self, guild_id: str, role_id: str, name: str = "", color: int = 0, hoist: int = 0, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "PATCH", f"/guilds/{guild_id}/roles/{role_id}",
            json_body={"name": name, "color": color, "hoist": hoist}, account_id=account_id,
        )

    async def delete_guild_role(self, guild_id: str, role_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("DELETE", f"/guilds/{guild_id}/roles/{role_id}", account_id=account_id)

    async def get_guild_api_permission(self, guild_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/guilds/{guild_id}/api_permission", account_id=account_id)

    async def demand_guild_api_permission(
        self, guild_id: str, channel_id: str, api_path: str, api_method: str, desc: str = "", account_id: Optional[str] = None
    ) -> dict:
        """申请接口调用权限"""
        body = {
            "channel_id": channel_id,
            "api_identify": {"path": api_path, "method": api_method},
            "desc": desc,
        }
        return await self._request("POST", f"/guilds/{guild_id}/api_permission/demand", json_body=body, account_id=account_id)

    # ---------- 子频道（Channel） ----------

    async def get_channels(self, guild_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/guilds/{guild_id}/channels", account_id=account_id)

    async def get_channel(self, channel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/channels/{channel_id}", account_id=account_id)

    async def create_channel(
        self, guild_id: str, name: str, channel_type: int = 0, subtype: int = 0,
        position: Optional[int] = None, private_type: Optional[int] = None,
        private_user_ids: Optional[List[str]] = None, speak_permission: Optional[int] = None,
        account_id: Optional[str] = None,
    ) -> dict:
        body: Dict[str, Any] = {"name": name, "type": channel_type, "subtype": subtype}
        if position is not None:
            body["position"] = position
        if private_type is not None:
            body["private_type"] = private_type
        if private_user_ids:
            body["private_user_ids"] = private_user_ids
        if speak_permission is not None:
            body["speak_permission"] = speak_permission
        return await self._request("POST", f"/guilds/{guild_id}/channels", json_body=body, account_id=account_id)

    async def update_channel(self, channel_id: str, account_id: Optional[str] = None, **fields) -> dict:
        """修改子频道：支持 name / position / parent_id / private_type / speak_permission"""
        allowed = {k: v for k, v in fields.items() if k in ("name", "position", "parent_id", "private_type", "speak_permission")}
        return await self._request("PATCH", f"/channels/{channel_id}", json_body=allowed, account_id=account_id)

    async def delete_channel(self, channel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("DELETE", f"/channels/{channel_id}", account_id=account_id)

    async def get_channel_pins(self, channel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/channels/{channel_id}/pins", account_id=account_id)

    async def pin_message(self, channel_id: str, message_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("POST", f"/channels/{channel_id}/pins/{message_id}", account_id=account_id)

    async def unpin_message(self, channel_id: str, message_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("DELETE", f"/channels/{channel_id}/pins/{message_id}", account_id=account_id)

    # ---------- 频道成员 ----------

    async def get_guild_members(self, guild_id: str, after: str = "", limit: int = 100, account_id: Optional[str] = None) -> dict:
        """获取频道成员列表（单页）"""
        return await self._request(
            "GET", f"/guilds/{guild_id}/members",
            params={"after": after or "0", "limit": str(limit)}, account_id=account_id,
        )

    async def get_guild_member(self, guild_id: str, member_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/guilds/{guild_id}/members/{member_id}", account_id=account_id)

    async def mute_guild_members(
        self, guild_id: str, mute_seconds: str, user_ids: Optional[List[str]] = None,
        mute_end_timestamp: str = "", account_id: Optional[str] = None,
    ) -> dict:
        """频道批量禁言（user_ids 为空时全频道禁言）"""
        body: Dict[str, Any] = {"mute_seconds": str(mute_seconds)}
        if mute_end_timestamp:
            body["mute_end_timestamp"] = str(mute_end_timestamp)
        if user_ids:
            body["user_ids"] = user_ids
        return await self._request("PUT", f"/guilds/{guild_id}/mute", json_body=body, account_id=account_id)

    async def mute_guild_member(self, guild_id: str, member_id: str, mute_seconds: str, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "PUT", f"/guilds/{guild_id}/members/{member_id}/mute",
            json_body={"mute_seconds": str(mute_seconds)}, account_id=account_id,
        )

    async def add_guild_member_role(self, guild_id: str, member_id: str, role_id: str, channel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "PUT", f"/guilds/{guild_id}/members/{member_id}/roles/{role_id}",
            json_body={"id": channel_id}, account_id=account_id,
        )

    async def remove_guild_member_role(self, guild_id: str, member_id: str, role_id: str, channel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "DELETE", f"/guilds/{guild_id}/members/{member_id}/roles/{role_id}",
            json_body={"id": channel_id}, account_id=account_id,
        )

    async def kick_guild_member(
        self, guild_id: str, member_id: str, add_blacklist: bool = False, delete_message_days: int = -1,
        account_id: Optional[str] = None,
    ) -> dict:
        body = {"add_blacklist": add_blacklist, "delete_message_days": delete_message_days}
        return await self._request(
            "DELETE", f"/guilds/{guild_id}/members/{member_id}", json_body=body, account_id=account_id
        )

    # ---------- 权限 / 公告 ----------

    async def get_channel_role_permissions(self, channel_id: str, role_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/channels/{channel_id}/roles/{role_id}/permissions", account_id=account_id)

    async def update_channel_role_permissions(
        self, channel_id: str, role_id: str, add: str = "", remove: str = "", account_id: Optional[str] = None
    ) -> dict:
        body: Dict[str, str] = {}
        if add:
            body["add"] = add
        if remove:
            body["remove"] = remove
        return await self._request(
            "PUT", f"/channels/{channel_id}/roles/{role_id}/permissions", json_body=body, account_id=account_id
        )

    async def get_channel_member_permissions(self, channel_id: str, member_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/channels/{channel_id}/members/{member_id}/permissions", account_id=account_id)

    async def update_channel_member_permissions(
        self, channel_id: str, member_id: str, add: str = "", remove: str = "", account_id: Optional[str] = None
    ) -> dict:
        body: Dict[str, str] = {}
        if add:
            body["add"] = add
        if remove:
            body["remove"] = remove
        return await self._request(
            "PUT", f"/channels/{channel_id}/members/{member_id}/permissions", json_body=body, account_id=account_id
        )

    async def create_announce(self, guild_id: str, channel_id: str, message_id: str = "", account_id: Optional[str] = None) -> dict:
        body = {"channel_id": channel_id}
        if message_id:
            body["message_id"] = message_id
        return await self._request("POST", f"/guilds/{guild_id}/announces", json_body=body, account_id=account_id)

    # ---------- 表态 ----------

    async def add_reaction(self, channel_id: str, message_id: str, emoji_type: int, emoji_id: str, account_id: Optional[str] = None) -> dict:
        """对消息表态（emoji_type: 1=系统表情 2=emoji）"""
        return await self._request(
            "PUT", f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji_type}/{emoji_id}",
            account_id=account_id,
        )

    async def delete_reaction(self, channel_id: str, message_id: str, emoji_type: int, emoji_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "DELETE", f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji_type}/{emoji_id}",
            account_id=account_id,
        )

    async def get_reaction_users(
        self, channel_id: str, message_id: str, emoji_type: int, emoji_id: str,
        cookie: str = "", limit: int = 20, account_id: Optional[str] = None,
    ) -> dict:
        params = {"limit": str(limit)}
        if cookie:
            params["cookie"] = cookie
        return await self._request(
            "GET", f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji_type}/{emoji_id}",
            params=params, account_id=account_id,
        )

    # ---------- 日程 ----------

    async def get_schedules(self, channel_id: str, since: str = "", account_id: Optional[str] = None) -> dict:
        return await self._request(
            "GET", f"/channels/{channel_id}/schedules", params={"since": since} if since else None,
            account_id=account_id,
        )

    async def get_schedule(self, channel_id: str, schedule_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/channels/{channel_id}/schedules/{schedule_id}", account_id=account_id)

    async def create_schedule(self, channel_id: str, schedule: dict, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "POST", f"/channels/{channel_id}/schedules", json_body={"schedule": schedule}, account_id=account_id
        )

    async def update_schedule(self, channel_id: str, schedule_id: str, schedule: dict, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "PATCH", f"/channels/{channel_id}/schedules/{schedule_id}",
            json_body={"schedule": schedule}, account_id=account_id,
        )

    async def delete_schedule(self, channel_id: str, schedule_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("DELETE", f"/channels/{channel_id}/schedules/{schedule_id}", account_id=account_id)

    # ---------- 帖子（论坛，私域） ----------

    async def get_threads(self, channel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/channels/{channel_id}/threads", account_id=account_id)

    async def get_thread(self, channel_id: str, thread_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/channels/{channel_id}/threads/{thread_id}", account_id=account_id)

    async def publish_thread(self, channel_id: str, title: str, content: str, thread_format: int = 3, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "POST", f"/channels/{channel_id}/threads",
            json_body={"title": title, "content": content, "format": thread_format}, account_id=account_id,
        )

    async def delete_thread(self, channel_id: str, thread_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("DELETE", f"/channels/{channel_id}/threads/{thread_id}", account_id=account_id)

    # ---------- 音频 ----------

    async def control_audio(self, channel_id: str, audio_url: str = "", text: str = "", status: int = 2, account_id: Optional[str] = None) -> dict:
        """音频控制（status: 0=开始 1=暂停 2=停止 3=上麦）"""
        body: Dict[str, Any] = {"status": status}
        if audio_url:
            body["audio_url"] = audio_url
        if text:
            body["text"] = text
        return await self._request("POST", f"/channels/{channel_id}/audio", json_body=body, account_id=account_id)

    async def mic_online(self, channel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("PUT", f"/channels/{channel_id}/mic", account_id=account_id)

    async def mic_offline(self, channel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("DELETE", f"/channels/{channel_id}/mic", account_id=account_id)

    # ---------- 频道私信 ----------

    async def create_dms(self, recipient_id: str, source_guild_id: str, account_id: Optional[str] = None) -> dict:
        """创建频道私信会话，返回 {guild_id, channel_id}（guild_id 用于 Send.To("dms", guild_id)）"""
        body = {"recipient_id": recipient_id, "source_guild_id": source_guild_id}
        return await self._request("POST", "/users/@me/dms", json_body=body, account_id=account_id)

    async def get_channel_message(self, channel_id: str, message_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/channels/{channel_id}/messages/{message_id}", account_id=account_id)

    # ---------- 群管理（v2，部分接口仅白名单机器人开放） ----------

    async def get_group_info_raw(self, group_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/v2/groups/{group_id}/info", account_id=account_id)

    async def get_group_bot_state(self, group_id: str, account_id: Optional[str] = None) -> dict:
        """获取机器人在群内的状态（是否管理员/消息接收设置等）"""
        return await self._request("GET", f"/v2/groups/{group_id}/bot_state", account_id=account_id)

    async def get_group_members(self, group_id: str, cursor: str = "", account_id: Optional[str] = None) -> dict:
        """获取群成员列表（单页，响应含 next_cursor）"""
        return await self._request(
            "GET", f"/v2/groups/{group_id}/members", params={"cursor": cursor} if cursor else None,
            account_id=account_id,
        )

    async def get_group_member(self, group_id: str, member_openid: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/v2/groups/{group_id}/members/{member_openid}", account_id=account_id)

    async def batch_remove_group_members(
        self, group_id: str, member_openids: List[str], add_to_blacklist: bool = False,
        account_id: Optional[str] = None,
    ) -> dict:
        """批量移出群成员"""
        body = {"member_openids": member_openids, "add_to_member_blacklist": add_to_blacklist}
        return await self._request("POST", f"/v2/groups/{group_id}/batch_remove_members", json_body=body, account_id=account_id)

    async def get_group_member_blacklist(self, group_id: str, cursor: str = "", limit: int = 20, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "GET", f"/v2/groups/{group_id}/member_blacklist",
            params={k: str(v) for k, v in {"cursor": cursor, "limit": limit}.items() if v},
            account_id=account_id,
        )

    async def update_group_member_blacklist(self, group_id: str, op: str, member_openids: List[str], account_id: Optional[str] = None) -> dict:
        """更新群黑名单（op: "add" / "del"）"""
        body = {"op": op, "member_openids": member_openids}
        return await self._request("POST", f"/v2/groups/{group_id}/member_blacklist", json_body=body, account_id=account_id)

    async def get_group_join_requests(self, group_id: str, cursor: str = "", limit: int = 20, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "GET", f"/v2/groups/{group_id}/join_request_list",
            params={k: str(v) for k, v in {"cursor": cursor, "limit": limit}.items() if v},
            account_id=account_id,
        )

    async def approve_group_join(
        self, group_id: str, member_openid: str, join_request_id: str = "",
        approve: bool = True, reject_reason: str = "", add_to_blacklist: bool = False,
        account_id: Optional[str] = None,
    ) -> dict:
        """审批入群申请（同意/拒绝，可附带拒绝理由）"""
        body: Dict[str, Any] = {"op": "approve" if approve else "decline"}
        if join_request_id:
            body["join_request_id"] = join_request_id
        if not approve and reject_reason:
            body["reject_reason"] = reject_reason
        if add_to_blacklist:
            body["add_to_member_blacklist"] = True
        return await self._request(
            "POST", f"/v2/groups/{group_id}/approval_join_request/{member_openid}",
            json_body=body, account_id=account_id,
        )

    async def get_group_restrict_setting(self, group_id: str, account_id: Optional[str] = None) -> dict:
        """获取群禁言设置（全局规则+成员状态）"""
        return await self._request("GET", f"/v2/groups/{group_id}/restrict_chat_setting", account_id=account_id)

    async def set_group_restrict(
        self, group_id: str, members: List[dict], account_id: Optional[str] = None
    ) -> dict:
        """设置群成员禁言

        :param members: [{"op": "add"/"update"/"del", "member_openid": "...", "mute_expire_at": 秒级时间戳(可选)}]
        """
        return await self._request(
            "POST", f"/v2/groups/{group_id}/restrict_chat_setting", json_body={"members": members},
            account_id=account_id,
        )

    async def get_join_approval_strategies(self, cursor: str = "", limit: int = 20, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "GET", "/v2/groups/join_approval_strategy",
            params={k: str(v) for k, v in {"cursor": cursor, "limit": limit}.items() if v},
            account_id=account_id,
        )

    async def create_join_approval_strategy(self, strategy: dict, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "POST", "/v2/groups/join_approval_strategy", json_body=strategy, account_id=account_id
        )

    async def update_join_approval_strategy(self, strategy_id: str, account_id: Optional[str] = None, **fields) -> dict:
        return await self._request(
            "PATCH", f"/v2/groups/join_approval_strategy/{strategy_id}", json_body=fields, account_id=account_id
        )

    async def delete_join_approval_strategy(self, strategy_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("DELETE", f"/v2/groups/join_approval_strategy/{strategy_id}", account_id=account_id)

    async def execute_join_approval_strategy(self, strategy_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request(
            "POST", f"/v2/groups/join_approval_strategy/{strategy_id}/execute", account_id=account_id
        )

    async def update_join_approval_strategy_whitelist(
        self, strategy_id: str, op: str, whitelist_users: List[str], account_id: Optional[str] = None
    ) -> dict:
        body = {"op": op, "whitelist_users": whitelist_users}
        return await self._request(
            "POST", f"/v2/groups/join_approval_strategy/{strategy_id}/whitelist_users",
            json_body=body, account_id=account_id,
        )

    # ---------- 自定义菜单与指令面板 ----------

    async def get_custom_menu(self, account_id: Optional[str] = None) -> dict:
        """查询全局自定义菜单（仅 C2C 单聊生效）"""
        return await self._request("GET", "/v2/menu", account_id=account_id)

    async def update_custom_menu(self, items: List[dict], account_id: Optional[str] = None) -> dict:
        """覆盖式修改全局自定义菜单

        :param items: 菜单项列表，类型 switch / send_message / link / menu（子菜单最多5项不可嵌套）
        """
        return await self._request("PUT", "/v2/menu", json_body={"menu": {"items": items}}, account_id=account_id)

    async def get_command_panels(self, scope: str, cursor: str = "", limit: int = 20, account_id: Optional[str] = None) -> dict:
        """查询指令面板列表（scope: "c2c" / "group" / "channel" / "dm"）"""
        params: Dict[str, str] = {"scope": scope, "limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/v2/panels", params=params, account_id=account_id)

    async def create_command_panel(
        self, scope: str, items: List[dict], remark: str = "", target_type: str = "all",
        user_openids: Optional[List[str]] = None, group_openids: Optional[List[str]] = None,
        account_id: Optional[str] = None,
    ) -> dict:
        """创建指令面板（每机器人最多20个；channel/dm 仅支持 target_type="all"）

        :param items: 面板项列表（command / link，链接必须 https:// 开头）
        """
        panel: Dict[str, Any] = {"items": items}
        if remark:
            panel["remark"] = remark
        body: Dict[str, Any] = {"scope": scope, "panel": panel, "target_type": target_type}
        if user_openids:
            body["user_openids"] = user_openids
        if group_openids:
            body["group_openids"] = group_openids
        return await self._request("POST", "/v2/panels", json_body=body, account_id=account_id)

    async def get_command_panel(self, panel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("GET", f"/v2/panels/{panel_id}", account_id=account_id)

    async def update_command_panel(self, panel_id: str, items: List[dict], remark: str = "", account_id: Optional[str] = None) -> dict:
        panel: Dict[str, Any] = {"items": items}
        if remark:
            panel["remark"] = remark
        return await self._request("PUT", f"/v2/panels/{panel_id}", json_body={"panel": panel}, account_id=account_id)

    async def delete_command_panel(self, panel_id: str, account_id: Optional[str] = None) -> dict:
        return await self._request("DELETE", f"/v2/panels/{panel_id}", account_id=account_id)

    async def update_command_panel_targets(
        self, panel_id: str, op: str, user_openids: Optional[List[str]] = None,
        group_openids: Optional[List[str]] = None, account_id: Optional[str] = None,
    ) -> dict:
        """增删面板关联对象（仅 c2c/group 且 target_type="specific" 的面板）"""
        body: Dict[str, Any] = {"op": op}
        if user_openids:
            body["user_openids"] = user_openids
        if group_openids:
            body["group_openids"] = group_openids
        return await self._request("PUT", f"/v2/panels/{panel_id}/target", json_body=body, account_id=account_id)
