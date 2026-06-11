import asyncio
import json
import time
from typing import Optional

from ErisPulse.Core import client
from ErisPulse.Core.Bases.websocket import WSMessage


class QQBotWebSocket:
    OP_HELLO = 10
    OP_IDENTIFY = 2
    OP_HEARTBEAT = 1
    OP_HEARTBEAT_ACK = 11
    OP_DISPATCH = 0
    OP_RESUME = 6
    OP_RECONNECT = 7
    OP_INVALID_SESSION = 9

    def __init__(self, adapter):
        self.adapter = adapter
        self.ws = None
        self.heartbeat_interval = 45000
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.listen_task: Optional[asyncio.Task] = None
        self.seq: Optional[int] = None
        self.session_id: Optional[str] = None
        self._connected = False
        self._token_refresh_task: Optional[asyncio.Task] = None
        self._reconnect_count = 0
        self._max_reconnect = 50
        self._closing = False

    async def connect(self):
        gateway_url = self.adapter.config.get("gateway_url", "wss://api.sgroup.qq.com/websocket/")
        await self._connect(gateway_url)

    async def _connect(self, url: str):
        try:
            self.ws = await client.ws_connect(url)
            self.adapter.logger.info("WebSocket 已连接到 QQBot 网关")
            self._connected = True

            msg = await self.ws.receive()
            if msg.type == WSMessage.TEXT:
                data = json.loads(msg.data)
                if data.get("op") == self.OP_HELLO:
                    inner = data.get("d", {})
                    self.heartbeat_interval = inner.get("heartbeat_interval", 45000)

                    if self.session_id and self.seq is not None:
                        await self._resume()
                    else:
                        await self._identify()

                    self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                    self.listen_task = asyncio.create_task(self._listen())

                    self._reconnect_count = 0
                else:
                    self.adapter.logger.error(f"未收到 Hello 消息: {data}")
            else:
                self.adapter.logger.error(f"未收到 Hello 消息: {msg.type}")

        except Exception as e:
            self.adapter.logger.error(f"WebSocket 连接失败: {e}")
            await self._reconnect()

    async def _identify(self):
        token = await self.adapter._ensure_token()
        payload = {
            "op": self.OP_IDENTIFY,
            "d": {
                "token": f"QQBot {token}",
                "intents": self.adapter._get_intents_value(),
                "shard": [0, 1],
            },
        }
        await self.ws.send_json(payload)
        self.adapter.logger.info("已发送 Identify")

    async def _resume(self):
        token = await self.adapter._ensure_token()
        payload = {
            "op": self.OP_RESUME,
            "d": {
                "token": f"QQBot {token}",
                "session_id": self.session_id,
                "seq": self.seq,
            },
        }
        await self.ws.send_json(payload)
        self.adapter.logger.info("已发送 Resume")

    async def _heartbeat_loop(self):
        try:
            while self._connected and self.ws and not self.ws.closed:
                heartbeat_payload = {
                    "op": self.OP_HEARTBEAT,
                    "d": self.seq,
                }
                try:
                    await self.ws.send_json(heartbeat_payload)
                except Exception as e:
                    self.adapter.logger.error(f"发送心跳失败: {e}")
                    break
                await asyncio.sleep(self.heartbeat_interval / 1000)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.adapter.logger.error(f"心跳循环异常: {e}")
            await self._reconnect()

    async def _listen(self):
        try:
            while self._connected:
                msg = await self.ws.receive()
                if msg.type == WSMessage.TEXT:
                    data = json.loads(msg.data)
                    await self._handle_message(data)
                elif msg.type in (WSMessage.CLOSE, WSMessage.ERROR):
                    self.adapter.logger.warning(f"WebSocket 关闭: {msg.type}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.adapter.logger.error(f"监听异常: {e}")
        finally:
            self._connected = False
            if not self._closing and (not self.listen_task or not self.listen_task.cancelled()):
                await self._reconnect()

    async def _handle_message(self, data: dict):
        op = data.get("op")
        t = data.get("t")
        d = data.get("d")
        s = data.get("s")

        if s is not None:
            self.seq = s

        if op == self.OP_DISPATCH:
            if t == "READY":
                self.session_id = d.get("session_id") if d else None
                user = d.get("user", {}) if d else {}
                self.adapter.bot_id = str(user.get("id", ""))
                if self.adapter._active_account:
                    self.adapter._active_account.bot_id = self.adapter.bot_id
                self.adapter.logger.info(f"QQBot 就绪, bot_id: {self.adapter.bot_id}")
                await self.adapter._on_connect()
            elif t == "RESUMED":
                self.adapter.logger.info("QQBot 会话已恢复")
            else:
                if d:
                    onebot_event = self.adapter.convert(d, t or "")
                    if onebot_event:
                        self.adapter._store_event_msg_id(onebot_event)
                        self.adapter.logger.debug(f"收到事件: {onebot_event}")
                        await self.adapter.sdk.adapter.emit(onebot_event)

        elif op == self.OP_HEARTBEAT_ACK:
            pass

        elif op == self.OP_RECONNECT:
            self.adapter.logger.warning("收到 Reconnect 指令，重新连接")
            await self._reconnect()

        elif op == self.OP_INVALID_SESSION:
            self.adapter.logger.warning("会话无效，重新 Identify")
            self.session_id = None
            self.seq = None
            await self._reconnect()

        elif op == self.OP_HELLO:
            data_inner = d if d else {}
            self.heartbeat_interval = data_inner.get("heartbeat_interval", 45000)

    async def _reconnect(self):
        if self._closing:
            return

        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None

        self._reconnect_count += 1
        if self._reconnect_count > self._max_reconnect:
            self.adapter.logger.error("已达到最大重连次数，停止重连")
            return

        wait_time = min(5 * (2 ** min(self._reconnect_count, 6)), 300)
        self.adapter.logger.warning(f"{wait_time}秒后尝试第 {self._reconnect_count} 次重连")
        await asyncio.sleep(wait_time)

        if self._closing:
            return

        try:
            if self.ws and not self.ws.closed:
                await self.ws.close()
        except Exception:
            pass

        gateway_url = self.adapter.config.get("gateway_url", "wss://api.sgroup.qq.com/websocket/")
        await self._connect(gateway_url)

    async def start_token_refresh(self):
        self._token_refresh_task = asyncio.create_task(self._token_refresh_loop())

    async def _token_refresh_loop(self):
        try:
            while True:
                await asyncio.sleep(7200 - 120)
                await self.adapter._refresh_token()
                self.adapter.logger.info("Access Token 已刷新")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.adapter.logger.error(f"Token 刷新异常: {e}")

    async def close(self):
        self._closing = True
        self._connected = False

        if self._token_refresh_task:
            self._token_refresh_task.cancel()
            try:
                await self._token_refresh_task
            except asyncio.CancelledError:
                pass
            self._token_refresh_task = None

        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None

        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass
            self.listen_task = None

        if self.ws and not self.ws.closed:
            await self.ws.close()

        self.adapter.logger.info("WebSocket 连接已关闭")
