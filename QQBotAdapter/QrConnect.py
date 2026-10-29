"""
QQ 官方「扫码一键接入」协议实现（QQBot 龙虾Bot Agent 接入）

协议流程（对齐官方 @tencent-connect/qqbot-connector 1.2.0）：
1. POST https://q.qq.com/lite/create_bind_task  body={"key": <32B随机base64>}
   → {"retcode":0,"data":{"task_id":...}}
2. 二维码 URL：https://q.qq.com/qqbot/openclaw/connect.html?task_id=<id>&source=<source>&_wv=2
3. POST https://q.qq.com/lite/poll_bind_result  body={"task_id":...}  （建议2秒轮询）
   → {"retcode":0,"data":{"status":0/1/2/3, "bot_appid", "bot_encrypt_secret", "user_openid"}}
   status: 0=无 1=等待扫码 2=完成 3=过期
4. status=2 时 AES-256-GCM 解密 bot_encrypt_secret：
   密文base64解码 → [12B nonce][ciphertext][16B tag]，key 为第1步的原始字节
   → 明文即 appSecret

不依赖第三方库以外的环境：AES-GCM 需要 cryptography（ErisPulse 环境普遍具备），
缺失时优雅降级提示。
"""
import asyncio
import base64
import os
from typing import Callable, Optional

from ErisPulse.Core import client

__all__ = ["QrConnectSession", "BindStatus"]

QQ_HOST = "q.qq.com"
CREATE_TASK_URL = f"https://{QQ_HOST}/lite/create_bind_task"
POLL_URL = f"https://{QQ_HOST}/lite/poll_bind_result"
QR_PAGE_URL = f"https://{QQ_HOST}/qqbot/openclaw/connect.html"
POLL_INTERVAL = 2.0


class BindStatus:
    NONE = 0
    PENDING = 1
    COMPLETED = 2
    EXPIRED = 3


def _generate_bind_key() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def _decrypt_secret(encrypt_secret_b64: str, key_b64: str) -> str:
    key = base64.b64decode(key_b64)
    blob = base64.b64decode(encrypt_secret_b64)
    nonce, tag, ciphertext = blob[:12], blob[-16:], blob[12:-16]
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key).decrypt(nonce, ciphertext + tag, None).decode("utf-8")


class QrConnectSession:
    """一次扫码接入会话：start() 拿二维码 → 前端展示 → poll_loop 等待扫码"""

    def __init__(self, source: str = ""):
        self.source = source
        self.task_id: Optional[str] = None
        self._key: Optional[str] = None
        self.qr_url: Optional[str] = None
        self._watch_task: Optional[asyncio.Task] = None

    async def start(self) -> str:
        """创建绑定任务，返回二维码 URL"""
        self._key = _generate_bind_key()
        resp = await client.post(CREATE_TASK_URL, json={"key": self._key}, timeout=10)
        data = await resp.json()
        if (data or {}).get("retcode") != 0:
            raise RuntimeError(f"create_bind_task 失败: {data}")
        task_id = str((data.get("data") or {}).get("task_id") or "")
        if not task_id:
            raise RuntimeError(f"create_bind_task 缺少 task_id: {data}")
        self.task_id = task_id
        sep = "&"
        self.qr_url = (
            f"{QR_PAGE_URL}?task_id={task_id}&source={self.source}{sep}_wv=2"
        )
        return self.qr_url

    async def poll(self) -> dict:
        """单次轮询：{"status": int, "appid"?, "secret"?, "openid"?}"""
        if not self.task_id:
            raise RuntimeError("尚未 start()")
        resp = await client.post(POLL_URL, json={"task_id": self.task_id}, timeout=10)
        data = await resp.json()
        if (data or {}).get("retcode") != 0:
            raise RuntimeError(f"poll_bind_result 失败: {data}")
        d = data.get("data") or {}
        out = {"status": int(d.get("status") or 0)}
        if out["status"] == BindStatus.COMPLETED:
            out["appid"] = str(d.get("bot_appid") or "")
            encrypt = d.get("bot_encrypt_secret") or ""
            out["secret"] = _decrypt_secret(encrypt, self._key) if encrypt else ""
            if d.get("user_openid"):
                out["openid"] = str(d["user_openid"])
        return out

    async def poll_loop(self, on_success: Callable[[dict], None],
                        on_expired: Optional[Callable[[], None]] = None,
                        max_rounds: int = 600):
        """轮询直到完成/过期/取消；完成回调 on_success(credentials dict)"""
        for _ in range(max_rounds):
            try:
                r = await self.poll()
            except Exception:
                await asyncio.sleep(POLL_INTERVAL)
                continue
            if r["status"] == BindStatus.COMPLETED:
                on_success(r)
                return
            if r["status"] == BindStatus.EXPIRED:
                if on_expired:
                    on_expired()
                return
            await asyncio.sleep(POLL_INTERVAL)

    def start_watcher(self, on_success, on_expired=None):
        """后台轮询（fire-and-forget，返回 Task 可取消）"""
        self._watch_task = asyncio.create_task(
            self.poll_loop(on_success, on_expired)
        )
        return self._watch_task

    def cancel(self):
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
