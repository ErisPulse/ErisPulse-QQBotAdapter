import re
import time
from datetime import datetime, timezone
from typing import Dict, Optional, List

from ErisPulse.Core.Bases import BaseConverter


class QQBotConverter(BaseConverter):
    """
    QQ官方机器人 原生事件 → OneBot12 事件转换器

    - 公共字段（id/time/platform/self/{platform}_raw）由 BaseConverter.build_base_event 构建
    - 支持消息 / 通知 / 请求（GROUP_JOIN_REQUEST）/ 论坛（私域）等事件
    - 无法识别的事件返回 type="unknown"（带 warning），不返回 None，保证原始数据不丢失
    """

    # 群/私聊富文本占位
    _V2_TOKEN_RE = re.compile(r'<qqbot-at-user id="([^"]+)"\s*/?>|<qqbot-at-everyone\s*/?>')
    # 频道富文本占位（@ 与 emoji）
    _GUILD_TOKEN_RE = re.compile(r"<@!?(\w+)>|<emoji:(\w+)>")

    def __init__(self, bot_id_getter=None):
        super().__init__(platform="qqbot")
        self._bot_id_getter = bot_id_getter
        self._event_type_map = {
            # ==================== 消息事件 ====================
            "C2C_MESSAGE_CREATE": ("message", "private"),
            "GROUP_AT_MESSAGE_CREATE": ("message", "group"),
            "GROUP_MESSAGE_CREATE": ("message", "group"),
            "AT_MESSAGE_CREATE": ("message", "channel"),
            "MESSAGE_CREATE": ("message", "channel"),
            "DIRECT_MESSAGE_CREATE": ("message", "private"),
            # ==================== 请求事件 ====================
            "GROUP_JOIN_REQUEST": ("request", "group"),
            # ==================== 好友/私聊通知 ====================
            "FRIEND_ADD": ("notice", "friend_add"),
            "FRIEND_DEL": ("notice", "friend_del"),
            "C2C_MSG_REJECT": ("notice", "private_block"),
            "C2C_MSG_RECEIVE": ("notice", "private_allow"),
            # ==================== 群通知 ====================
            "GROUP_ADD_ROBOT": ("notice", "group_increase"),
            "GROUP_DEL_ROBOT": ("notice", "group_decrease"),
            "GROUP_MSG_REJECT": ("notice", "group_block"),
            "GROUP_MSG_RECEIVE": ("notice", "group_allow"),
            "GROUP_MEMBER_ADD": ("notice", "group_member_increase"),
            "GROUP_MEMBER_REMOVE": ("notice", "group_member_decrease"),
            # ==================== 频道通知 ====================
            "GUILD_CREATE": ("notice", "guild_create"),
            "GUILD_UPDATE": ("notice", "guild_update"),
            "GUILD_DELETE": ("notice", "guild_delete"),
            "CHANNEL_CREATE": ("notice", "channel_create"),
            "CHANNEL_UPDATE": ("notice", "channel_update"),
            "CHANNEL_DELETE": ("notice", "channel_delete"),
            "GUILD_MEMBER_ADD": ("notice", "guild_member_increase"),
            "GUILD_MEMBER_UPDATE": ("notice", "guild_member_update"),
            "GUILD_MEMBER_REMOVE": ("notice", "guild_member_decrease"),
            "AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER": ("notice", "qqbot_channel_enter"),
            "AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT": ("notice", "qqbot_channel_exit"),
            "MESSAGE_REACTION_ADD": ("notice", "qqbot_reaction_add"),
            "MESSAGE_REACTION_REMOVE": ("notice", "qqbot_reaction_remove"),
            "INTERACTION_CREATE": ("notice", "qqbot_interaction"),
            "MESSAGE_AUDIT_PASS": ("notice", "qqbot_audit_pass"),
            "MESSAGE_AUDIT_REJECT": ("notice", "qqbot_audit_reject"),
            "AUDIO_START": ("notice", "qqbot_audio_start"),
            "AUDIO_FINISH": ("notice", "qqbot_audio_finish"),
            "AT_MESSAGE_DELETE": ("notice", "qqbot_message_delete"),
            "PUBLIC_MESSAGE_DELETE": ("notice", "qqbot_message_delete"),
            "DIRECT_MESSAGE_DELETE": ("notice", "qqbot_message_delete"),
            # ==================== 论坛通知（私域） ====================
            "FORUM_THREAD_CREATE": ("notice", "qqbot_forum_thread_create"),
            "FORUM_THREAD_UPDATE": ("notice", "qqbot_forum_thread_update"),
            "FORUM_THREAD_DELETE": ("notice", "qqbot_forum_thread_delete"),
            "FORUM_POST_CREATE": ("notice", "qqbot_forum_post_create"),
            "FORUM_POST_DELETE": ("notice", "qqbot_forum_post_delete"),
            "FORUM_REPLY_CREATE": ("notice", "qqbot_forum_reply_create"),
            "FORUM_REPLY_DELETE": ("notice", "qqbot_forum_reply_delete"),
            "FORUM_PUBLISH_AUDIT_RESULT": ("notice", "qqbot_forum_audit"),
        }

    def convert(self, raw_event: Dict, ws_event_type: str = "") -> Optional[Dict]:
        if not isinstance(raw_event, dict):
            return None

        raw_type = ws_event_type or self._detect_raw_type(raw_event)
        event_info = self._event_type_map.get(raw_type)
        if event_info is None:
            return self._create_unknown_event(raw_event, raw_type or "unknown")

        event_type, detail_type = event_info

        base_event = self.build_base_event(raw_event, raw_type)
        base_event["time"] = self._parse_timestamp(raw_event.get("timestamp")) or int(time.time())
        base_event["id"] = str(raw_event.get("event_id") or raw_event.get("id") or base_event["id"])
        base_event["type"] = event_type
        base_event["detail_type"] = detail_type
        if self._bot_id_getter:
            base_event["self"]["user_id"] = str(self._bot_id_getter() or "")

        handler = getattr(self, f"_handle_{event_type}", None)
        if handler:
            return handler(raw_event, base_event, raw_type)

        return base_event

    # ==================== 类型探测 ====================

    def _detect_raw_type(self, raw_event: Dict) -> str:
        for key in raw_event:
            if key not in ("id", "timestamp", "version", "shard", "event_id") and key.isupper():
                return key
        for key, value in raw_event.items():
            if isinstance(value, str) and value.isupper() and "_" in value and key in ("type", "event_type"):
                return value
        return ""

    # ==================== 消息事件 ====================

    def _handle_message(self, raw_event: Dict, base_event: Dict, raw_type: str) -> Dict:
        detail_type = base_event["detail_type"]
        author = raw_event.get("author", {}) or {}

        if raw_type == "C2C_MESSAGE_CREATE":
            base_event["user_id"] = str(author.get("user_openid", ""))
            base_event["user_nickname"] = ""
            base_event["message_id"] = raw_event.get("id", "")
            base_event["qqbot_openid"] = author.get("user_openid", "")
            base_event["qqbot_event_id"] = raw_event.get("id", "")
        elif raw_type in ("GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_CREATE"):
            base_event["user_id"] = str(author.get("member_openid", ""))
            base_event["user_nickname"] = ""
            base_event["group_id"] = raw_event.get("group_openid", "")
            base_event["message_id"] = raw_event.get("id", "")
            base_event["qqbot_group_openid"] = raw_event.get("group_openid", "")
            base_event["qqbot_member_openid"] = author.get("member_openid", "")
            base_event["qqbot_event_id"] = raw_event.get("id", "")
            base_event["qqbot_is_at_message"] = raw_type == "GROUP_AT_MESSAGE_CREATE"
        elif raw_type in ("AT_MESSAGE_CREATE", "MESSAGE_CREATE"):
            base_event["user_id"] = str(author.get("id", author.get("user_openid", "")))
            base_event["user_nickname"] = author.get("nick", author.get("username", ""))
            base_event["channel_id"] = raw_event.get("channel_id", "")
            base_event["group_id"] = raw_event.get("guild_id", "")
            base_event["message_id"] = raw_event.get("id", "")
        elif raw_type == "DIRECT_MESSAGE_CREATE":
            base_event["user_id"] = str(author.get("id", author.get("user_openid", "")))
            base_event["user_nickname"] = author.get("nick", author.get("username", ""))
            base_event["message_id"] = raw_event.get("id", "")
            base_event["group_id"] = raw_event.get("guild_id", "")
            base_event["qqbot_guild_id"] = raw_event.get("guild_id", "")

        message_segments = self._parse_content(raw_event, raw_type)

        for mention in raw_event.get("mentions", []):
            message_segments.append({
                "type": "mention",
                "data": {
                    "user_id": str(mention.get("id", "")),
                    "user_name": mention.get("nick", mention.get("username", "")),
                },
            })

        # "定义上就是@机器人"的事件：保证存在机器人自身的 mention 段，
        # 使框架的 is_at_message()/on_at_message 能正确识别
        if raw_type in ("GROUP_AT_MESSAGE_CREATE", "AT_MESSAGE_CREATE"):
            self._ensure_bot_mention(base_event, message_segments, raw_type)
        elif raw_type == "GROUP_MESSAGE_CREATE":
            # 开通"接收全部群消息"后，@消息也可能以该事件推送：
            # 若 content 中 at 标记命中 bot_id，则识别为@消息
            self_id = str(self._bot_id_getter() or "") if self._bot_id_getter else ""
            if self_id and any(
                seg.get("type") == "mention" and str(seg.get("data", {}).get("user_id", "")) == self_id
                for seg in message_segments
            ):
                base_event["qqbot_is_at_message"] = True

        for attachment in raw_event.get("attachments", []) or []:
            message_segments.append(self._attachment_to_segment(attachment))

        base_event["message"] = message_segments
        base_event["alt_message"] = self._generate_alt_message(message_segments)
        return base_event

    def _parse_content(self, raw_event: Dict, raw_type: str) -> List[Dict]:
        """将平台富文本 content 解析为 OneBot12 消息段"""
        content = raw_event.get("content", "") or ""
        is_guild = raw_type in ("AT_MESSAGE_CREATE", "MESSAGE_CREATE", "DIRECT_MESSAGE_CREATE")
        pattern = self._GUILD_TOKEN_RE if is_guild else self._V2_TOKEN_RE

        segments: List[Dict] = []
        pos = 0
        for match in pattern.finditer(content):
            if match.start() > pos and content[pos:match.start()].strip():
                segments.append(self.text(content[pos:match.start()].strip()))
            if is_guild:
                if match.group(1) is not None:
                    segments.append({"type": "mention", "data": {"user_id": match.group(1)}})
                elif match.group(2) is not None:
                    segments.append({"type": "face", "data": {"id": match.group(2)}})
            else:
                if match.group(0).startswith("<qqbot-at-user"):
                    segments.append({"type": "mention", "data": {"user_id": match.group(1)}})
                else:
                    segments.append({"type": "mention_all", "data": {}})
            pos = match.end()
        if pos < len(content) and content[pos:].strip():
            segments.append(self.text(content[pos:].strip()))

        if not segments and content.strip():
            segments.append(self.text(content.strip()))
        return segments

    def _attachment_to_segment(self, attachment: Dict) -> Dict:
        content_type = attachment.get("content_type", "")
        url = attachment.get("url", "")
        if content_type.startswith("image"):
            seg_type = "image"
        elif content_type.startswith("video"):
            seg_type = "video"
        elif content_type.startswith("audio"):
            seg_type = "voice"
        else:
            seg_type = "file"
        return {
            "type": seg_type,
            "data": {"url": url, "qqbot_attachment": attachment},
        }

    def _ensure_bot_mention(self, base_event: Dict, segments: List[Dict], raw_type: str):
        """
        保证消息中存在机器人自身的 mention 段

        QQ官方群消息的"被@"事实由事件名承载（GROUP_AT_MESSAGE_CREATE），
        content 中通常没有机器人自身的 @ 标记；而框架的 is_at_message()/
        on_at_message 依赖扫描 user_id == self.user_id 的 mention 段。
        因此对定义上就是@消息的事件，转换时补齐机器人 mention 段：

        - 已有 mention 段且 id 与 bot_id 一致 → 无需处理
        - 群消息含其他 @ 标记 → 首个标记视为机器人（群空间 openid 保留到 qqbot_openid）
        - 无任何标记 → 前置注入 mention(bot_id)
        """
        self_id = str(self._bot_id_getter() or "") if self._bot_id_getter else ""
        base_event["qqbot_is_at_message"] = True
        if not self_id:
            return

        for seg in segments:
            if seg.get("type") == "mention" and str(seg.get("data", {}).get("user_id", "")) == self_id:
                return

        at_indexes = [i for i, seg in enumerate(segments) if seg.get("type") == "mention"]
        if at_indexes and raw_type == "GROUP_AT_MESSAGE_CREATE":
            # 群空间 openid 与 bot_id 不在一个 id 体系，无法对账；
            # 约定首个 @ 标记为机器人自身，保留原始 openid 供 API 使用
            seg = segments[at_indexes[0]]
            original_id = str(seg.get("data", {}).get("user_id", ""))
            seg["data"]["user_id"] = self_id
            if original_id and original_id != self_id:
                seg["data"]["qqbot_openid"] = original_id
            return

        segments.insert(0, {"type": "mention", "data": {"user_id": self_id}})

    # ==================== 请求事件 ====================

    def _handle_request(self, raw_event: Dict, base_event: Dict, raw_type: str) -> Dict:
        if raw_type == "GROUP_JOIN_REQUEST":
            verify_info = raw_event.get("verify_info", {}) or {}
            base_event["request_id"] = str(raw_event.get("join_request_id", ""))
            base_event["user_id"] = str(raw_event.get("member_openid", ""))
            base_event["user_nickname"] = raw_event.get("username", "")
            base_event["group_id"] = raw_event.get("group_openid", "")
            base_event["comment"] = verify_info.get("verify_message", "")
            base_event["qqbot_join_request_id"] = raw_event.get("join_request_id", "")
            base_event["qqbot_group_openid"] = raw_event.get("group_openid", "")
            base_event["qqbot_member_openid"] = raw_event.get("member_openid", "")
            base_event["qqbot_apply_source"] = raw_event.get("apply_source", "")
            base_event["qqbot_invited_by"] = raw_event.get("invited_by", "")
            base_event["qqbot_verify_method"] = verify_info.get("method", "")
            base_event["qqbot_verify_qa"] = verify_info.get("review_qa_list", [])
        return base_event

    # ==================== 通知事件 ====================

    def _handle_notice(self, raw_event: Dict, base_event: Dict, raw_type: str) -> Dict:
        if raw_type == "GROUP_MEMBER_ADD":
            base_event["user_id"] = str(raw_event.get("member_openid") or raw_event.get("user_openid", ""))
            base_event["group_id"] = raw_event.get("group_openid", "")
            base_event["operator_id"] = str(raw_event.get("op_member_openid", ""))
        elif raw_type == "GROUP_MEMBER_REMOVE":
            base_event["user_id"] = str(raw_event.get("member_openid") or raw_event.get("user_openid", ""))
            base_event["group_id"] = raw_event.get("group_openid", "")
            base_event["operator_id"] = str(raw_event.get("op_member_openid", ""))

        elif raw_type in ("GROUP_ADD_ROBOT", "GROUP_DEL_ROBOT", "GROUP_MSG_REJECT", "GROUP_MSG_RECEIVE"):
            base_event["group_id"] = raw_event.get("group_openid", "")
            base_event["operator_id"] = str(raw_event.get("op_member_openid", ""))
        elif raw_type in ("FRIEND_ADD", "FRIEND_DEL"):
            base_event["user_id"] = str(raw_event.get("openid", ""))
            base_event["user_nickname"] = ""
        elif raw_type in ("C2C_MSG_REJECT", "C2C_MSG_RECEIVE"):
            base_event["user_id"] = str(raw_event.get("openid", ""))

        elif raw_type == "GUILD_MEMBER_ADD":
            user = raw_event.get("user", {}) or {}
            base_event["user_id"] = str(user.get("id", ""))
            base_event["user_nickname"] = user.get("nickname", user.get("username", ""))
            base_event["group_id"] = raw_event.get("guild_id", "")
            base_event["operator_id"] = str(raw_event.get("op_user_id", ""))
        elif raw_type in ("GUILD_MEMBER_UPDATE", "GUILD_MEMBER_REMOVE"):
            user = raw_event.get("user", {}) or {}
            base_event["user_id"] = str(user.get("id", ""))
            base_event["user_nickname"] = user.get("nickname", user.get("username", ""))
            base_event["group_id"] = raw_event.get("guild_id", "")
            base_event["operator_id"] = str(raw_event.get("op_user_id", ""))

        elif raw_type in ("CHANNEL_CREATE", "CHANNEL_UPDATE", "CHANNEL_DELETE"):
            base_event["channel_id"] = str(raw_event.get("channel_id") or raw_event.get("id", ""))
            base_event["group_id"] = raw_event.get("guild_id", "")
            base_event["qqbot_channel_name"] = raw_event.get("name", "")
            base_event["qqbot_channel_type"] = raw_event.get("channel_type", "")
            base_event["operator_id"] = str(raw_event.get("op_user_id", ""))
        elif raw_type in ("GUILD_CREATE", "GUILD_UPDATE", "GUILD_DELETE"):
            base_event["group_id"] = str(raw_event.get("id", ""))
            base_event["qqbot_guild_name"] = raw_event.get("name", "")
            base_event["operator_id"] = str(raw_event.get("op_user_id", ""))
        elif raw_type in ("AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER", "AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT"):
            base_event["channel_id"] = str(raw_event.get("channel_id") or raw_event.get("id", ""))
            base_event["group_id"] = raw_event.get("guild_id", "")
            base_event["user_id"] = str(raw_event.get("user_id", ""))

        elif raw_type == "INTERACTION_CREATE":
            base_event["qqbot_interaction_id"] = raw_event.get("id", "")
            base_event["qqbot_interaction_type"] = raw_event.get("type", "")
            base_event["qqbot_interaction_data"] = raw_event.get("data", {})
            base_event["qqbot_interaction_scene"] = raw_event.get("scene", "")
            resolved = (raw_event.get("data", {}) or {}).get("resolved", {}) or {}
            base_event["qqbot_button_id"] = resolved.get("button_id", "")
            base_event["qqbot_button_data"] = resolved.get("button_data", "")
            if resolved.get("message_id"):
                base_event["message_id"] = resolved.get("message_id", "")
        elif raw_type in ("MESSAGE_AUDIT_PASS", "MESSAGE_AUDIT_REJECT"):
            base_event["qqbot_audit_id"] = raw_event.get("audit_id", "")
            base_event["message_id"] = raw_event.get("message_id", "")
            base_event["channel_id"] = raw_event.get("channel_id", "")
            base_event["group_id"] = raw_event.get("guild_id", "")
            if raw_type == "MESSAGE_AUDIT_REJECT":
                base_event["qqbot_audit_reject_reason"] = raw_event.get("audit_reject_reason", "")
        elif raw_type in ("MESSAGE_REACTION_ADD", "MESSAGE_REACTION_REMOVE"):
            base_event["user_id"] = str(raw_event.get("user_id", ""))
            target = raw_event.get("target", {}) or {}
            emoji = raw_event.get("emoji", {}) or {}
            base_event["channel_id"] = raw_event.get("channel_id", "")
            base_event["group_id"] = raw_event.get("guild_id", "")
            base_event["message_id"] = str(target.get("id", ""))
            base_event["qqbot_reaction_target_type"] = target.get("type", "")
            base_event["qqbot_reaction_emoji"] = {"id": emoji.get("id", ""), "type": emoji.get("type", "")}
        elif raw_type in ("AT_MESSAGE_DELETE", "PUBLIC_MESSAGE_DELETE", "DIRECT_MESSAGE_DELETE"):
            base_event["message_id"] = raw_event.get("id", raw_event.get("message_id", ""))
            base_event["operator_id"] = str(raw_event.get("op_user_id", ""))
            base_event["channel_id"] = raw_event.get("channel_id", "")
            base_event["group_id"] = raw_event.get("guild_id", "")
        elif raw_type in ("AUDIO_START", "AUDIO_FINISH"):
            base_event["group_id"] = raw_event.get("guild_id", "")
            base_event["channel_id"] = raw_event.get("channel_id", "")
            base_event["qqbot_audio_url"] = raw_event.get("audio_url", "")
            base_event["qqbot_audio_text"] = raw_event.get("text", "")

        elif raw_type.startswith("FORUM_") or raw_type.startswith("OPEN_FORUM_"):
            base_event["group_id"] = raw_event.get("guild_id", "")
            base_event["channel_id"] = raw_event.get("channel_id", "")
            for key in ("thread_info", "post_info", "reply_info"):
                info = raw_event.get(key)
                if info:
                    base_event["message_id"] = str(
                        info.get("thread_id") or info.get("post_id") or info.get("reply_id", "")
                    )
                    base_event["qqbot_forum_content"] = info.get("content", "")
                    base_event["qqbot_forum_title"] = info.get("title", "")
                    break
            if raw_type == "FORUM_PUBLISH_AUDIT_RESULT":
                base_event["qqbot_forum_audit_result"] = raw_event.get("result", "")
                base_event["qqbot_forum_audit_err_msg"] = raw_event.get("err_msg", "")

        return base_event

    # ==================== 辅助 ====================

    def _create_unknown_event(self, raw_event: Dict, raw_type: str) -> Dict:
        event = self.build_base_event(raw_event, raw_type)
        event["time"] = self._parse_timestamp(raw_event.get("timestamp")) or int(time.time())
        event["type"] = "unknown"
        event["detail_type"] = "unknown"
        event["warning"] = f"Unsupported event type: {raw_type}"
        event["alt_message"] = "This event type is not supported by this system."
        return event

    def _parse_timestamp(self, timestamp) -> int:
        if isinstance(timestamp, (int, float)):
            ts = int(timestamp)
            return ts // 1000 if ts > 10**12 else ts
        if isinstance(timestamp, str):
            try:
                ts = int(timestamp)
                return ts // 1000 if ts > 10**12 else ts
            except ValueError:
                pass
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp())
            except (ValueError, TypeError):
                pass
        return 0

    def _generate_alt_message(self, segments: List[Dict]) -> str:
        parts = []
        for seg in segments:
            seg_type = seg["type"]
            data = seg.get("data", {})
            if seg_type == "text":
                parts.append(data.get("text", ""))
            elif seg_type == "image":
                parts.append("[图片]")
            elif seg_type == "video":
                parts.append("[视频]")
            elif seg_type == "voice":
                parts.append("[语音]")
            elif seg_type == "file":
                parts.append("[文件]")
            elif seg_type in ("at", "mention"):
                parts.append(f"@{data.get('user_name', data.get('user_id', ''))}")
            elif seg_type == "mention_all":
                parts.append("@全体成员")
            elif seg_type == "reply":
                parts.append("[回复]")
            elif seg_type == "face":
                parts.append(f"[表情:{data.get('id', '')}]")
        return " ".join(parts).strip()
