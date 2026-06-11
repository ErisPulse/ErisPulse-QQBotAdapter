import asyncio
import json
import time as _time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from ErisPulse import sdk
from ErisPulse.Core import client
from ErisPulse.runtime.config_schema import BotAccountConfig

from .Converter import QQBotConverter
from .WebSocket import QQBotWebSocket


@dataclass
class QQBotConfig(BotAccountConfig):
    """QQBot 账户配置"""

    appid: str = field(
        default="",
        metadata={
            "description": "QQ机器人应用ID",
            "required": True,
            "webui": {"widget": "text", "group": "basic", "order": 1},
        },
    )
    secret: str = field(
        default="",
        metadata={
            "description": "QQ机器人客户端密钥",
            "required": True,
            "secret": True,
            "webui": {"widget": "password", "group": "basic", "order": 2},
        },
    )
    sandbox: bool = field(
        default=False,
        metadata={
            "description": "是否使用沙盒环境",
            "webui": {"widget": "switch", "group": "connection", "order": 3},
        },
    )


@dataclass
class QQBotAdapterConfig:
    """QQBot 适配器全局配置"""

    intents: str = field(
        default="[1, 30, 25]",
        metadata={
            "description": "订阅的 intents 位列表（JSON格式）",
            "webui": {"widget": "text", "group": "connection", "order": 1},
        },
    )
    gateway_url: str = field(
        default="wss://api.sgroup.qq.com/websocket/",
        metadata={
            "description": "WebSocket 网关地址",
            "webui": {"widget": "text", "group": "connection", "order": 2},
        },
    )


class QQBotAdapter(sdk.BaseAdapter):
    """
    QQ官方机器人适配器

    通过 WebSocket 长连接接收事件，整合群聊、私聊、频道等多种场景
    """

    _platform = "qqbot"
    AccountConfigClass = QQBotConfig
    ConfigClass = QQBotAdapterConfig

    class Send(sdk.BaseAdapter.Send):

        def __init__(self, adapter, target_type=None, target_id=None, account_id=None):
            super().__init__(adapter, target_type, target_id, account_id)
            self._keyboard = None

        def Keyboard(self, keyboard: dict):
            self._keyboard = keyboard
            return self

        def _reset_modifiers(self):
            self._keyboard = None

        def Text(self, text: str):
            return self.Raw_ob12([{"type": "text", "data": {"text": text}}])

        def Image(self, file: bytes | str):
            return self.Raw_ob12([{"type": "image", "data": {"file": file}}])

        def Audio(self, file: bytes | str):
            return self.Raw_ob12([{"type": "audio", "data": {"file": file}}])

        def Voice(self, file: bytes | str):
            return self.Audio(file)

        def Video(self, file: bytes | str):
            return self.Raw_ob12([{"type": "video", "data": {"file": file}}])

        def File(self, file: bytes | str):
            return self.Raw_ob12([{"type": "file", "data": {"file": file}}])

        def Markdown(self, content: str):
            return self.Raw_ob12([{"type": "markdown", "data": {"content": content}}])

        def Ark(self, template_id: int, kv: list):
            return self.Raw_ob12([{"type": "ark", "data": {"template_id": template_id, "kv": kv}}])

        def Embed(self, embed_data: dict):
            return self.Raw_ob12([{"type": "embed", "data": embed_data}])

        def Raw_ob12(self, message, **kwargs):
            return asyncio.create_task(self._do_send_raw_ob12(message, **kwargs))

        async def _do_send_raw_ob12(self, message, **kwargs):
            text_parts = []
            media_info = None
            msg_type = 0
            markdown_data = None
            ark_data = None
            embed_data = None

            for segment in message:
                seg_type = segment.get("type")
                data = segment.get("data", {})

                if seg_type == "text":
                    text_parts.append(data.get("text", ""))
                elif seg_type == "image":
                    file = data.get("file", data.get("url", ""))
                    if isinstance(file, bytes):
                        media_info = await self._adapter._upload_media(file, self._target_type, self._target_id, 1)
                    elif file:
                        media_info = await self._adapter._upload_media(file, self._target_type, self._target_id, 1)
                    if media_info:
                        msg_type = 7
                elif seg_type == "voice":
                    file = data.get("file", data.get("url", ""))
                    if isinstance(file, (bytes, str)) and file:
                        media_info = await self._adapter._upload_media(file, self._target_type, self._target_id, 3)
                    if media_info:
                        msg_type = 7
                elif seg_type == "video":
                    file = data.get("file", data.get("url", ""))
                    if isinstance(file, (bytes, str)) and file:
                        media_info = await self._adapter._upload_media(file, self._target_type, self._target_id, 2)
                    if media_info:
                        msg_type = 7
                elif seg_type == "file":
                    file = data.get("file", data.get("url", ""))
                    if isinstance(file, (bytes, str)) and file:
                        media_info = await self._adapter._upload_media(file, self._target_type, self._target_id, 4)
                    if media_info:
                        msg_type = 7
                elif seg_type == "audio":
                    file = data.get("file", data.get("url", ""))
                    if isinstance(file, (bytes, str)) and file:
                        media_info = await self._adapter._upload_media(file, self._target_type, self._target_id, 3)
                    if media_info:
                        msg_type = 7
                elif seg_type == "markdown":
                    msg_type = 2
                    markdown_data = data
                elif seg_type == "ark":
                    msg_type = 3
                    ark_data = data
                elif seg_type == "embed":
                    msg_type = 4
                    embed_data = data
                elif seg_type == "mention":
                    uid = data.get("user_id", "")
                    if uid:
                        text_parts.append(f"<@{uid}>")

            for uid in self._at_user_ids:
                text_parts.append(f"<@{uid}>")
            if self._at_all:
                text_parts.insert(0, "@所有人")

            content = "".join(text_parts) or " "
            msg_id = self._reply_message_id or kwargs.get("msg_id", "")
            if not msg_id and self._target_type and self._target_id:
                msg_id = self._adapter._pending_msg_ids.get(f"{self._target_type}:{self._target_id}", "")
            params = {"msg_type": msg_type, "content": content if msg_type in (0, 7) else "", "msg_id": msg_id}

            if msg_type == 2 and markdown_data:
                params["markdown"] = {"content": markdown_data.get("content", "")}
            elif msg_type == 3 and ark_data:
                params["ark"] = {"template_id": ark_data.get("template_id", 0), "kv": ark_data.get("kv", [])}
            elif msg_type == 4 and embed_data:
                params["embed"] = embed_data
            elif msg_type == 7 and media_info:
                params["media"] = {"file_info": media_info}

            if self._keyboard:
                params["keyboard"] = self._keyboard

            endpoint = self._get_send_endpoint()
            if not endpoint:
                self._reset_modifiers()
                return self._adapter.make_error(retcode=10003, message="无法确定发送目标")

            self._reset_modifiers()
            return await self._adapter.call_api(endpoint=endpoint, **params)

        def _get_send_endpoint(self) -> Optional[str]:
            if self._target_type == "user":
                return f"/v2/users/{self._target_id}/messages"
            elif self._target_type == "group":
                return f"/v2/groups/{self._target_id}/messages"
            elif self._target_type == "channel":
                return f"/channels/{self._target_id}/messages"
            elif self._target_type == "dms":
                return f"/dms/{self._target_id}/messages"
            return None

    def _get_config_key(self) -> str:
        return "QQBot_Adapter"

    def _load_accounts(self) -> dict:
        from ErisPulse.runtime.config_schema import dict_to_dataclass
        from ErisPulse.Core.config import config as config_mgr

        key = f"{self._get_config_key()}.accounts"
        data = config_mgr.getConfig(key)

        if not data:
            old_config = config_mgr.getConfig(self._get_config_key())
            if old_config:
                self.logger.info("检测到旧格式配置，迁移到新格式")
                data = {
                    "default": {
                        "appid": old_config.get("appid", ""),
                        "secret": old_config.get("secret", ""),
                        "sandbox": old_config.get("sandbox", False),
                        "enabled": True,
                    }
                }
                try:
                    config_mgr.setConfig(key, data)
                except Exception as e:
                    self.logger.error(f"保存迁移配置失败: {e}")
            else:
                self.logger.info("未找到配置，创建默认配置模板")
                data = {
                    "default": {
                        "appid": "YOUR_APPID",
                        "secret": "YOUR_CLIENT_SECRET",
                        "sandbox": False,
                        "enabled": True,
                    }
                }
                try:
                    config_mgr.setConfig(key, data)
                    self.logger.warning("QQBot适配器配置不存在，已自动创建默认配置")
                except Exception as e:
                    self.logger.error(f"保存默认配置失败: {e}")

        accounts = {}
        for name, account_data in data.items():
            if not isinstance(account_data, dict):
                continue

            appid = account_data.get("appid", "")
            secret = account_data.get("secret", "")

            if appid in ("YOUR_APPID", "") and secret in ("YOUR_CLIENT_SECRET", ""):
                self.logger.warning(f"跳过模板账户: {name}")
                continue

            instance = dict_to_dataclass(QQBotConfig, account_data)
            instance.name = name
            accounts[name] = instance

        return accounts

    def __init__(self, sdk_instance=None):
        super().__init__(sdk_instance)

        self.adapter = sdk.adapter
        self._access_token = None
        self._token_expires = 0
        self.bot_id = ""
        self.ws_client: Optional[QQBotWebSocket] = None
        self._heartbeat_meta_task: Optional[asyncio.Task] = None
        self._pending_msg_ids: Dict[str, str] = {}

        self._active_account_name = None
        self._active_account = None

        converter = QQBotConverter(bot_id_getter=lambda: self.bot_id)
        self.convert = converter.convert

    def _get_active_config(self) -> dict:
        if self._active_account:
            return {
                "appid": self._active_account.appid,
                "secret": self._active_account.secret,
                "sandbox": self._active_account.sandbox,
            }
        return {}

    @property
    def config(self):
        return self._get_active_config()

    @config.setter
    def config(self, value):
        pass

    def _get_base_url(self) -> str:
        sandbox = self._active_account.sandbox if self._active_account else False
        if sandbox:
            return "https://sandbox.api.sgroup.qq.com"
        return "https://api.sgroup.qq.com"

    def _get_intents_value(self) -> int:
        adapter_config = self._config_instance
        if adapter_config:
            import json as _json
            try:
                intents = _json.loads(adapter_config.intents)
            except Exception:
                intents = [1, 30, 25]
        else:
            intents = [1, 30, 25]

        value = 0
        for intent in intents:
            value |= (1 << intent)
        return value

    def _get_gateway_url(self) -> str:
        adapter_config = self._config_instance
        if adapter_config and adapter_config.gateway_url:
            return adapter_config.gateway_url
        return "wss://api.sgroup.qq.com/websocket/"

    async def _ensure_token(self) -> str:
        if self._access_token and _time.time() < self._token_expires - 120:
            return self._access_token
        await self._refresh_token()
        return self._access_token

    async def _refresh_token(self):
        url = "https://bots.qq.com/app/getAppAccessToken"
        payload = {
            "appId": self._active_account.appid,
            "clientSecret": self._active_account.secret,
        }
        try:
            resp = await client.post(url, json=payload)
            data = await resp.json()
            self._access_token = data.get("access_token", "")
            expires_in = int(data.get("expires_in", 7200))
            self._token_expires = _time.time() + expires_in
            self.logger.debug("Access Token 已获取/刷新")
        except Exception as e:
            self.logger.error(f"获取 Access Token 失败: {e}")
            raise

    async def _upload_media(self, file, target_type: str, target_id: str, file_type: int) -> Optional[str]:
        url = self._get_base_url()
        if target_type == "user":
            url += f"/v2/users/{target_id}/files"
        elif target_type == "group":
            url += f"/v2/groups/{target_id}/files"
        else:
            return None

        token = await self._ensure_token()
        headers = {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}

        payload = {"file_type": file_type, "srv_send_msg": False}

        if isinstance(file, str) and file.startswith(("http://", "https://")):
            payload["url"] = file
        elif isinstance(file, bytes):
            import base64
            payload["file_data"] = base64.b64encode(file).decode("utf-8")
        elif isinstance(file, str):
            try:
                import os
                if os.path.isfile(file):
                    with open(file, "rb") as f:
                        file_bytes = f.read()
                    import base64
                    payload["file_data"] = base64.b64encode(file_bytes).decode("utf-8")
                else:
                    self.logger.error(f"文件不存在: {file}")
                    return None
            except Exception as e:
                self.logger.error(f"读取本地文件失败: {e}")
                return None

        try:
            resp = await client.post(url, json=payload, headers=headers)
            data = await resp.json()
            self.logger.debug(f"上传媒体响应: {data}")
            file_info = data.get("file_info", "")
            if not file_info:
                self.logger.error(f"上传媒体失败: {data}")
                return None
            return file_info
        except Exception as e:
            self.logger.error(f"上传媒体异常: {e}")
            return None

    async def call_api(self, endpoint: str, _account_id: str = None, **params):
        token = await self._ensure_token()
        url = f"{self._get_base_url()}{endpoint}"
        headers = {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}

        try:
            resp = await client.post(url, json=params, headers=headers)
            raw_response = await resp.json()

            self.logger.debug(f"QQBot API 请求: {url}")
            self.logger.debug(f"QQBot API 响应: {raw_response}")

            if not isinstance(raw_response, dict):
                return self.make_error(
                    retcode=34000,
                    message=f"API 返回了意外格式: {type(raw_response)}",
                    raw=raw_response,
                )

            code = raw_response.get("code", 0)
            success = 200 <= resp.status < 300 and code == 0
            msg_id = raw_response.get("id", raw_response.get("data", {}).get("id", ""))

            if success:
                return self.make_response(
                    data=raw_response.get("data", raw_response),
                    message_id=str(msg_id) if msg_id else "",
                    raw=raw_response,
                )
            else:
                return self.make_error(
                    retcode=code or 34000,
                    message=raw_response.get("message", "Unknown QQBot API error"),
                    raw=raw_response,
                )

        except asyncio.TimeoutError:
            self.logger.error(f"QQBot API 请求超时: {endpoint}")
            return self.make_error(retcode=32000, message="请求超时")
        except Exception as e:
            self.logger.error(f"调用 QQBot API 失败: {e}")
            return self.make_error(retcode=33000, message=f"API调用失败: {str(e)}")

    def _store_event_msg_id(self, event: Dict):
        if event.get("type") != "message":
            return
        detail_type = event.get("detail_type", "")
        msg_id = event.get("message_id", "")
        if not msg_id:
            return
        if detail_type == "group" and "group_id" in event:
            self._pending_msg_ids[f"group:{event['group_id']}"] = msg_id
        elif detail_type == "private":
            user_id = event.get("user_id", "")
            if user_id:
                self._pending_msg_ids[f"user:{user_id}"] = msg_id
        elif detail_type == "channel":
            channel_id = event.get("channel_id", "")
            if channel_id:
                self._pending_msg_ids[f"channel:{channel_id}"] = msg_id

    async def _on_connect(self):
        await self.emit_meta("connect", self.bot_id)
        self._heartbeat_meta_task = asyncio.create_task(self._heartbeat_meta_loop())

    async def _heartbeat_meta_loop(self):
        try:
            while True:
                await asyncio.sleep(30)
                await self.emit_meta("heartbeat", self.bot_id)
        except asyncio.CancelledError:
            pass

    async def start(self):
        enabled = self.enabled_accounts
        if not enabled:
            self.logger.warning("没有找到启用的账户配置")
            return

        first_name = next(iter(enabled))
        self._active_account_name = first_name
        self._active_account = enabled[first_name]

        try:
            await self._ensure_token()
        except Exception as e:
            self.logger.error(f"初始化 Token 失败: {e}")
            raise

        self.ws_client = QQBotWebSocket(self)
        await self.ws_client.connect()
        await self.ws_client.start_token_refresh()
        self.logger.info("QQBot 适配器已启动")

    async def shutdown(self):
        if self.bot_id:
            await self.emit_meta("disconnect", self.bot_id)

        if self._heartbeat_meta_task:
            self._heartbeat_meta_task.cancel()
            try:
                await self._heartbeat_meta_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_meta_task = None

        if self.ws_client:
            await self.ws_client.close()
            self.ws_client = None

        self.logger.info("QQBot 适配器已关闭")
