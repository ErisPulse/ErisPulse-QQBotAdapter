import asyncio
import json
from typing import Optional

from ErisPulse.Core import client
from ErisPulse.Core.Bases.websocket import WSMessage


class QQBotWebSocket:
    """QQ官方机器人 WebSocket 网关客户端（每账户一个实例，自动重连/恢复会话）"""

    OP_DISPATCH = 0
    OP_HEARTBEAT = 1
    OP_IDENTIFY = 2
    OP_RESUME = 6
    OP_RECONNECT = 7
    OP_INVALID_SESSION = 9
    OP_HELLO = 10
    OP_HEARTBEAT_ACK = 11

    MAX_RECONNECT = 50
    HELLO_TIMEOUT = 30
    RECV_TIMEOUT = 120

    def __init__(self, adapter, account_name: str, account_runtime):
        self.adapter = adapter
        self.name = account_name
        self.rt = account_runtime
        self.ws = None
        self.heartbeat_interval = 45000
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.meta_heartbeat_task: Optional[asyncio.Task] = None
        self.seq: Optional[int] = None
        self.session_id: Optional[str] = None
        self._connected = False
        self._closing = False
        self._reconnect_count = 0

    @property
    def connected(self) -> bool:
        return self._connected

    # ==================== 主循环 ====================

    async def run(self):
        """阻塞式运行：连接 → 监听 → 断线自动重连（指数退避）"""
        while not self._closing:
            gateway = await self._resolve_gateway()
            if not await self._connect(gateway):
                if not await self._wait_reconnect():
                    break
                continue

            await self._listen()
            await self._cleanup_connection()

            if self._closing:
                break
            if not await self._wait_reconnect():
                break

    async def _resolve_gateway(self) -> str:
        cfg = self.rt.config
        if cfg.gateway_url:
            return cfg.gateway_url
        result = await self.adapter._request("GET", "/gateway/bot", account_id=self.name)
        if result.get("status") == "ok" and isinstance(result.get("data"), dict):
            url = result["data"].get("url", "")
            if url:
                return url
        self.adapter.logger.warning(
            f"账户 {self.name} 动态获取网关失败({result.get('message', '')})，使用默认网关"
        )
        return "wss://api.sgroup.qq.com/websocket/"

    async def _connect(self, url: str) -> bool:
        try:
            self.ws = await client.ws_connect(url)
            self.adapter.logger.info(f"账户 {self.name} WebSocket 已连接到 QQBot 网关")
        except Exception as e:
            self.adapter.logger.error(f"账户 {self.name} WebSocket 连接失败: {e}")
            return False

        try:
            msg = await asyncio.wait_for(self.ws.receive(), timeout=self.HELLO_TIMEOUT)
        except asyncio.TimeoutError:
            self.adapter.logger.error(f"账户 {self.name} 等待 Hello 超时")
            await self._close_ws()
            return False

        if msg.type != WSMessage.TEXT:
            self.adapter.logger.error(f"账户 {self.name} 未收到 Hello 消息: {msg.type}")
            await self._close_ws()
            return False

        data = json.loads(msg.data)
        if data.get("op") != self.OP_HELLO:
            self.adapter.logger.error(f"账户 {self.name} 收到非 Hello 包: {data}")
            await self._close_ws()
            return False

        inner = data.get("d", {}) or {}
        self.heartbeat_interval = inner.get("heartbeat_interval", 45000)

        if self.session_id and self.seq is not None:
            await self._resume()
        else:
            await self._identify()

        self._connected = True
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return True

    async def _identify(self):
        token = await self.adapter._ensure_token(self.rt)
        payload = {
            "op": self.OP_IDENTIFY,
            "d": {
                "token": f"QQBot {token}",
                "intents": self.adapter._get_intents_value(),
                "shard": [0, 1],
            },
        }
        await self.ws.send_json(payload)
        self.adapter.logger.info(f"账户 {self.name} 已发送 Identify")

    async def _resume(self):
        token = await self.adapter._ensure_token(self.rt)
        payload = {
            "op": self.OP_RESUME,
            "d": {
                "token": f"QQBot {token}",
                "session_id": self.session_id,
                "seq": self.seq,
            },
        }
        await self.ws.send_json(payload)
        self.adapter.logger.info(f"账户 {self.name} 已发送 Resume (seq={self.seq})")

    async def _heartbeat_loop(self):
        try:
            while self._connected and self.ws and not self.ws.closed:
                try:
                    await self.ws.send_json({"op": self.OP_HEARTBEAT, "d": self.seq})
                except Exception as e:
                    self.adapter.logger.error(f"账户 {self.name} 发送心跳失败: {e}")
                    break
                await asyncio.sleep(self.heartbeat_interval / 1000)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.adapter.logger.error(f"账户 {self.name} 心跳循环异常: {e}")

    async def _meta_heartbeat_loop(self):
        try:
            while True:
                await asyncio.sleep(30)
                if self.rt.bot_id:
                    await self.adapter.emit_meta("heartbeat", self.rt.bot_id)
        except asyncio.CancelledError:
            pass

    async def _listen(self):
        try:
            while self._connected and not self._closing:
                try:
                    msg = await asyncio.wait_for(self.ws.receive(), timeout=self.RECV_TIMEOUT)
                except asyncio.TimeoutError:
                    self.adapter.logger.warning(f"账户 {self.name} {self.RECV_TIMEOUT}s 未收到网关消息，触发重连")
                    break
                if msg.type == WSMessage.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except (ValueError, TypeError):
                        continue
                    await self._handle_message(data)
                elif msg.type in (WSMessage.CLOSE, WSMessage.ERROR):
                    self.adapter.logger.warning(f"账户 {self.name} WebSocket 关闭: {msg.type}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.adapter.logger.error(f"账户 {self.name} 监听异常: {e}")
        finally:
            self._connected = False

    async def _handle_message(self, data: dict):
        op = data.get("op")
        t = data.get("t")
        d = data.get("d")
        s = data.get("s")

        if s is not None:
            self.seq = s

        if op == self.OP_DISPATCH:
            if t == "READY":
                self.session_id = (d or {}).get("session_id")
                user = (d or {}).get("user", {}) or {}
                self.rt.bot_id = str(user.get("id", ""))
                self.rt.user_name = user.get("username", "")
                if not self.adapter.bot_id:
                    self.adapter.bot_id = self.rt.bot_id
                self._reconnect_count = 0
                self.adapter.logger.info(f"账户 {self.name} QQBot 就绪, bot_id: {self.rt.bot_id}")
                await self.adapter._on_account_ready(self.rt)
                if self.meta_heartbeat_task is None or self.meta_heartbeat_task.done():
                    self.meta_heartbeat_task = asyncio.create_task(self._meta_heartbeat_loop())
            elif t == "RESUMED":
                self._reconnect_count = 0
                self.adapter.logger.info(f"账户 {self.name} 会话已恢复")
            elif d is not None:
                await self.adapter._dispatch_event(d, t or "", self.name)

        elif op == self.OP_HEARTBEAT_ACK:
            pass

        elif op == self.OP_RECONNECT:
            self.adapter.logger.warning(f"账户 {self.name} 收到 Reconnect 指令，保留会话重连")
            await self._close_ws()

        elif op == self.OP_INVALID_SESSION:
            self.adapter.logger.warning(f"账户 {self.name} 会话无效，将重新 Identify")
            self.session_id = None
            self.seq = None
            await self._close_ws()

        elif op == self.OP_HELLO:
            self.heartbeat_interval = (d or {}).get("heartbeat_interval", 45000)

    # ==================== 断线与清理 ====================

    async def _wait_reconnect(self) -> bool:
        self._reconnect_count += 1
        if self._reconnect_count > self.MAX_RECONNECT:
            self.adapter.logger.error(f"账户 {self.name} 已达到最大重连次数({self.MAX_RECONNECT})，停止重连")
            return False
        wait_time = min(5 * (2 ** min(self._reconnect_count, 6)), 300)
        self.adapter.logger.warning(
            f"账户 {self.name} {wait_time}秒后尝试第 {self._reconnect_count} 次重连"
        )
        await asyncio.sleep(wait_time)
        return not self._closing

    async def _cleanup_connection(self):
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None
        await self._close_ws()

    async def _close_ws(self):
        self._connected = False
        if self.ws is not None:
            try:
                if not self.ws.closed:
                    await self.ws.close()
            except Exception:
                pass
            self.ws = None

    async def close(self):
        """停止运行并释放资源"""
        self._closing = True
        self._connected = False

        for task in (self.heartbeat_task, self.meta_heartbeat_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self.heartbeat_task = None
        self.meta_heartbeat_task = None

        await self._close_ws()
        self.adapter.logger.info(f"账户 {self.name} WebSocket 连接已关闭")
