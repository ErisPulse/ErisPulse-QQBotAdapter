import asyncio
import json
import time as _time
from typing import Optional

OP_DISPATCH = 0
OP_SIGN_VERIFY = 13


class _Ed25519:
    """
    Webhook 签名工具

    与官方规则保持一致（参照 qq-official-bot/src/ed25519.ts）：
    - 私钥种子 = secret 循环重复至不少于32字节后截取前32字节
    - 验签：对原始 UTF-8 消息（timestamp + body）验签
    - 应答签名（op=13 校验）：对 (event_ts + plain_token) 的 hex 字符串签名
    """

    def __init__(self, secret: str):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        seed = secret or ""
        while len(seed) < 32:
            seed = seed * 2
        self._private = Ed25519PrivateKey.from_private_bytes(seed[:32].encode("utf-8"))
        self._public = self._private.public_key()

    def sign(self, message: str) -> str:
        """challenge 应答签名（官方规则：对消息的 hex 字符串 UTF-8 字节签名）"""
        content = message.encode("utf-8").hex()
        return self._private.sign(content.encode("ascii")).hex()

    def sign_raw(self, message: str) -> str:
        """对原始 UTF-8 字节签名（与官方服务端对入站请求的签名语义一致，测试/调试用）"""
        return self._private.sign(message.encode("utf-8")).hex()

    def verify(self, signature_hex: str, message: str) -> bool:
        """验签入站请求（官方规则：对原始 UTF-8 消息 timestamp + body 验签）"""
        try:
            self._public.verify(bytes.fromhex(signature_hex), message.encode("utf-8"))
            return True
        except Exception:
            return False


class QQBotWebhook:
    """
    QQ官方机器人 Webhook 接入（HTTP 回调，Ed25519 验签）

    通过 ErisPulse router 注册 HTTP 路由，处理：
    - op=13 签名验证（回调地址配置校验）
    - op=0  事件分发（转为 OneBot12 事件并 emit）
    """

    def __init__(self, adapter, account_name: str, account_runtime):
        self.adapter = adapter
        self.name = account_name
        self.rt = account_runtime
        self._ed25519: Optional[_Ed25519] = None
        self._module = adapter.platform or "qqbot"
        self._path = ""
        self.registered = False
        self._keepalive_task: Optional[asyncio.Task] = None

    @property
    def path(self) -> str:
        return self._path

    async def start(self):
        try:
            self._ed25519 = _Ed25519(self.rt.config.secret)
        except ImportError:
            self.adapter.logger.error(
                f"账户 {self.name} Webhook 模式需要 cryptography 库（pip install cryptography）"
            )
            return
        except Exception as e:
            self.adapter.logger.error(f"账户 {self.name} 初始化 Ed25519 失败: {e}")
            return

        self._path = self._resolve_path()
        try:
            self.adapter.sdk.router.register_http_route(
                module_name=self._module,
                path=self._path,
                handler=self._handle,
                methods=["POST"],
                summary=f"QQBot Webhook ({self.name})",
                description="QQ官方机器人事件回调（Ed25519 验签）",
            )
        except Exception as e:
            self.adapter.logger.error(f"账户 {self.name} 注册 Webhook 路由失败: {e}")
            return

        self.registered = True
        try:
            info = self.adapter.sdk.adapter.get_connection_info(self._module)
            urls = (info or {}).get("urls") or (info or {}).get("routes") or info
            self.adapter.logger.info(f"账户 {self.name} Webhook 回调地址: {urls}")
        except Exception:
            self.adapter.logger.info(f"账户 {self.name} Webhook 路由已注册: {self._module}{self._path}")

        if self.rt.bot_id:
            try:
                await self.adapter.emit_meta("connect", self.rt.bot_id, user_name=self.rt.user_name)
            except Exception:
                pass

        self._keepalive_task = asyncio.create_task(self._token_keepalive_loop())
        await self._keepalive_task

    def _resolve_path(self) -> str:
        base = (self.rt.config.webhook_path or "/webhook").strip()
        if not base.startswith("/"):
            base = "/" + base
        hook_accounts = [
            n for n, rt in self.adapter._runtimes.items() if rt.config.mode == "webhook"
        ]
        if len(hook_accounts) > 1 and not base.rstrip("/").endswith("/" + self.name):
            base = base.rstrip("/") + "/" + self.name
        return base

    async def _handle(self, request):
        try:
            body = await request.body()
            text = body.decode("utf-8", errors="replace")
        except Exception:
            return self._json_response({"code": -1, "message": "invalid body"}, 400)

        signature = request.headers.get("X-Signature-Ed25519", "")
        timestamp = request.headers.get("X-Signature-Timestamp", "")

        if not self._ed25519 or not signature or not timestamp:
            return self._json_response({"code": -1, "message": "missing signature"}, 400)
        if not self._ed25519.verify(signature, timestamp + text):
            self.adapter.logger.warning(f"账户 {self.name} Webhook 签名验证失败")
            return self._json_response({"code": -1, "message": "invalid signature"}, 401)

        try:
            packet = json.loads(text)
        except ValueError:
            return self._json_response({"code": -1, "message": "invalid json"}, 400)

        op = packet.get("op")

        if op == OP_SIGN_VERIFY:
            d = packet.get("d", {}) or {}
            plain_token = d.get("plain_token", "")
            event_ts = str(d.get("event_ts", ""))
            signed = self._ed25519.sign(event_ts + plain_token)
            return self._json_response({"plain_token": plain_token, "signature": signed}, 200)

        if op == OP_DISPATCH:
            t = packet.get("t", "")
            d = packet.get("d")
            if isinstance(d, dict):
                try:
                    await self.adapter._dispatch_event(d, t, self.name)
                except Exception as e:
                    self.adapter.logger.error(f"账户 {self.name} Webhook 事件处理异常: {e}")
            return self._json_response({"code": 0, "message": "success"}, 200)

        return self._json_response({"code": -1, "message": f"unknown op: {op}"}, 400)

    @staticmethod
    def _json_response(payload: dict, status_code: int = 200):
        try:
            from fastapi.responses import JSONResponse

            return JSONResponse(content=payload, status_code=status_code)
        except ImportError:
            return payload

    async def _token_keepalive_loop(self):
        try:
            while True:
                remaining = self.rt.token_expires - _time.time() - 45
                await asyncio.sleep(max(60, min(remaining, 3600)))
                try:
                    await self.adapter._ensure_token(self.rt)
                except Exception as e:
                    self.adapter.logger.warning(f"账户 {self.name} Webhook 模式刷新 Token 失败: {e}")
        except asyncio.CancelledError:
            pass

    def stop(self):
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        if self.registered:
            try:
                self.adapter.sdk.router.unregister_http_route(self._module, self._path)
            except Exception:
                pass
            self.registered = False
