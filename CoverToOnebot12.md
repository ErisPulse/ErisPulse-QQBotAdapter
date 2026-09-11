# QQBot适配器与OneBot12协议的转换对照

## QQBot特有事件类型

QQBot平台提供以下事件类型，可在消息处理中检测使用：

### 1. 消息事件

| QQBot事件类型 | eventType | 说明 | 转换后 |
|---|---|---|---|
| C2C_MESSAGE_CREATE | 私聊消息 | 用户发送的私聊消息 | OneBot12 `message` 事件，`detail_type` 为 `private` |
| GROUP_AT_MESSAGE_CREATE | 群@消息 | 群内用户@机器人发送的消息 | OneBot12 `message` 事件，`detail_type` 为 `group` |
| GROUP_MESSAGE_CREATE | 群消息 | 群内非@机器人消息（仅白名单机器人） | OneBot12 `message` 事件，`detail_type` 为 `group`，附 `qqbot_is_at_message=false` |
| AT_MESSAGE_CREATE | 频道@消息 | 频道内@机器人发送的消息（公域） | OneBot12 `message` 事件，`detail_type` 为 `channel` |
| MESSAGE_CREATE | 频道消息 | 频道内用户发送的消息（私域） | OneBot12 `message` 事件，`detail_type` 为 `channel` |
| DIRECT_MESSAGE_CREATE | 私信消息 | 频道私信消息 | OneBot12 `message` 事件，`detail_type` 为 `private` |

### 2. 请求事件

| QQBot事件类型 | 说明 | 转换后 |
|---|---|---|
| GROUP_JOIN_REQUEST | 用户申请加入群聊 | OneBot12 `request` 事件，`detail_type` 为 `group`，`request_id` 为 `join_request_id`；可通过 `Request DSL` 或 `event.approve()/reject()` 审批 |

请求事件字段：`request_id`、`user_id`（申请人member_openid）、`user_nickname`（username）、`group_id`（群openid）、`comment`（验证消息）、`qqbot_apply_source`（申请来源）、`qqbot_verify_method` 等。

### 3. 通知事件

| QQBot事件类型 | 说明 | 转换后 |
|---|---|---|
| FRIEND_ADD | 用户添加机器人为好友 | OneBot12 `notice` 事件，`detail_type` 为 `friend_add` |
| FRIEND_DEL | 用户删除机器人好友 | OneBot12 `notice` 事件，`detail_type` 为 `friend_del` |
| C2C_MSG_REJECT | 用户拒绝机器人私聊 | OneBot12 `notice` 事件，`detail_type` 为 `private_block` |
| C2C_MSG_RECEIVE | 用户允许机器人私聊 | OneBot12 `notice` 事件，`detail_type` 为 `private_allow` |
| GROUP_ADD_ROBOT | 群添加机器人 | OneBot12 `notice` 事件，`detail_type` 为 `group_increase` |
| GROUP_DEL_ROBOT | 群移除机器人 | OneBot12 `notice` 事件，`detail_type` 为 `group_decrease` |
| GROUP_MSG_REJECT | 群拒绝机器人消息 | OneBot12 `notice` 事件，`detail_type` 为 `group_block` |
| GROUP_MSG_RECEIVE | 群允许机器人消息 | OneBot12 `notice` 事件，`detail_type` 为 `group_allow` |
| GROUP_MEMBER_ADD | 群成员加入（新增，需 GROUP_MEMBER intent） | OneBot12 `notice` 事件，`detail_type` 为 `group_member_increase` |
| GROUP_MEMBER_REMOVE | 群成员退出（新增，需 GROUP_MEMBER intent） | OneBot12 `notice` 事件，`detail_type` 为 `group_member_decrease` |
| GUILD_MEMBER_ADD | 频道成员加入 | OneBot12 `notice` 事件，`detail_type` 为 `guild_member_increase` |
| GUILD_MEMBER_UPDATE | 频道成员更新 | OneBot12 `notice` 事件，`detail_type` 为 `guild_member_update` |
| GUILD_MEMBER_REMOVE | 频道成员退出 | OneBot12 `notice` 事件，`detail_type` 为 `guild_member_decrease` |
| GUILD_CREATE | 频道服务器创建 | OneBot12 `notice` 事件，`detail_type` 为 `guild_create` |
| GUILD_UPDATE | 频道服务器更新 | OneBot12 `notice` 事件，`detail_type` 为 `guild_update` |
| GUILD_DELETE | 频道服务器删除 | OneBot12 `notice` 事件，`detail_type` 为 `guild_delete` |
| CHANNEL_CREATE | 子频道创建 | OneBot12 `notice` 事件，`detail_type` 为 `channel_create` |
| CHANNEL_UPDATE | 子频道更新 | OneBot12 `notice` 事件，`detail_type` 为 `channel_update` |
| CHANNEL_DELETE | 子频道删除 | OneBot12 `notice` 事件，`detail_type` 为 `channel_delete` |
| AUDIO_OR_LIVE_CHANNEL_MEMBER_ENTER | 用户进入音频/直播子频道（新增） | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_channel_enter` |
| AUDIO_OR_LIVE_CHANNEL_MEMBER_EXIT | 用户离开音频/直播子频道（新增） | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_channel_exit` |

> **5.0 破坏性变更**：`GUILD_MEMBER_*`（频道成员）与 `GROUP_MEMBER_*`（群成员）现已区分，频道成员事件 detail_type 从 `group_member_*` 更名为 `guild_member_*`。

### 4. QQBot平台特有通知事件

| QQBot事件类型 | 说明 | 转换后 |
|---|---|---|
| MESSAGE_REACTION_ADD | 消息表情回应添加 | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_reaction_add`（含 `message_id`/`user_id`/`qqbot_reaction_emoji`） |
| MESSAGE_REACTION_REMOVE | 消息表情回应移除 | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_reaction_remove` |
| INTERACTION_CREATE | 交互事件（按钮点击等） | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_interaction`（含 `qqbot_button_id`/`qqbot_button_data`） |
| MESSAGE_AUDIT_PASS | 消息审核通过 | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_audit_pass` |
| MESSAGE_AUDIT_REJECT | 消息审核拒绝 | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_audit_reject` |
| AUDIO_START | 音频开始播放 | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_audio_start` |
| AUDIO_FINISH | 音频播放结束 | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_audio_finish` |
| AT_MESSAGE_DELETE | @消息被删除 | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_message_delete` |
| PUBLIC_MESSAGE_DELETE | 公开消息被删除 | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_message_delete` |
| DIRECT_MESSAGE_DELETE | 私信消息被删除 | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_message_delete` |
| FORUM_THREAD_CREATE/UPDATE/DELETE | 论坛主帖变更（私域） | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_forum_thread_create/update/delete` |
| FORUM_POST_CREATE/DELETE | 论坛帖子变更（私域） | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_forum_post_create/delete` |
| FORUM_REPLY_CREATE/DELETE | 论坛回复变更（私域） | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_forum_reply_create/delete` |
| FORUM_PUBLISH_AUDIT_RESULT | 论坛审核结果（私域） | OneBot12 `notice` 事件，`detail_type` 为 `qqbot_forum_audit` |
| OPEN_FORUM_* | 开放论坛事件（仅记录原始数据） | OneBot12 `notice` 事件，`detail_type` 为 `unknown`（数据在 `qqbot_raw`） |

### 事件处理示例

```python
from ErisPulse.Core.Event import notice, message

# 处理消息事件
@message.on_message()
async def handle_message(event):
    if event.get("platform") != "qqbot":
        return

    detail_type = event.get("detail_type")

    if detail_type == "private":
        text = event.get_text()
        # 处理私聊消息...
    elif detail_type == "group":
        # 处理群@消息...
        group_id = event.get("group_id")
    elif detail_type == "channel":
        # 处理频道消息...
        channel_id = event.get("channel_id")

# 处理通知事件
@notice.on_notice()
async def handle_notice(event):
    if event.get("platform") != "qqbot":
        return

    detail_type = event.get("detail_type")

    if detail_type == "friend_add":
        user_id = event.get_user_id()
    elif detail_type == "group_increase":
        group_id = event.get("group_id")
    elif detail_type == "qqbot_interaction":
        interaction_id = event.get("qqbot_interaction_id", "")
        interaction_type = event.get("qqbot_interaction_type", "")
        interaction_data = event.get("qqbot_interaction_data", {})
    elif detail_type == "qqbot_audit_pass":
        audit_id = event.get("qqbot_audit_id", "")
        message_id = event.get("qqbot_message_id", "")
    elif detail_type == "qqbot_audit_reject":
        audit_id = event.get("qqbot_audit_id", "")
        reject_reason = event.get("qqbot_audit_reject_reason", "")
    elif detail_type == "qqbot_message_delete":
        message_id = event.get("message_id", "")
```

---

## 消息事件转换对照

### 1. 私聊消息（C2C_MESSAGE_CREATE）

原始事件:
```json
{
  "id": "msg_id_example",
  "author": {
    "user_openid": "USER_OPENID"
  },
  "content": "Hello",
  "timestamp": "2026-04-25T12:00:00+08:00",
  "attachments": []
}
```

转换后:
```json
{
  "id": "msg_id_example",
  "time": 1745558400,
  "type": "message",
  "detail_type": "private",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "C2C_MESSAGE_CREATE",
  "user_id": "USER_OPENID",
  "user_nickname": "",
  "message_id": "msg_id_example",
  "qqbot_openid": "USER_OPENID",
  "qqbot_event_id": "msg_id_example",
  "qqbot_reply_token": "",
  "message": [
    {
      "type": "text",
      "data": {
        "text": "Hello"
      }
    }
  ],
  "alt_message": "Hello"
}
```

### 2. 群@消息（GROUP_AT_MESSAGE_CREATE）

原始事件:
```json
{
  "id": "group_msg_id_example",
  "author": {
    "member_openid": "MEMBER_OPENID"
  },
  "content": "你好",
  "group_openid": "GROUP_OPENID",
  "timestamp": "2026-04-25T12:00:00+08:00",
  "attachments": []
}
```

转换后:
```json
{
  "id": "group_msg_id_example",
  "time": 1745558400,
  "type": "message",
  "detail_type": "group",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "GROUP_AT_MESSAGE_CREATE",
  "user_id": "MEMBER_OPENID",
  "user_nickname": "",
  "group_id": "GROUP_OPENID",
  "message_id": "group_msg_id_example",
  "qqbot_group_openid": "GROUP_OPENID",
  "qqbot_member_openid": "MEMBER_OPENID",
  "qqbot_event_id": "group_msg_id_example",
  "qqbot_reply_token": "",
  "message": [
    {
      "type": "text",
      "data": {
        "text": "你好"
      }
    }
  ],
  "alt_message": "你好"
}
```

### 3. 频道@消息（AT_MESSAGE_CREATE）

原始事件:
```json
{
  "id": "channel_msg_id_example",
  "author": {
    "user_openid": "USER_OPENID",
    "id": "USER_ID",
    "nick": "用户昵称"
  },
  "content": "频道消息",
  "channel_id": "CHANNEL_ID",
  "guild_id": "GUILD_ID",
  "timestamp": "2026-04-25T12:00:00+08:00",
  "attachments": [],
  "mentions": [
    {"id": "MENTIONED_USER_ID", "nick": "被@用户昵称"}
  ]
}
```

转换后:
```json
{
  "id": "channel_msg_id_example",
  "time": 1745558400,
  "type": "message",
  "detail_type": "channel",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "AT_MESSAGE_CREATE",
  "user_id": "USER_OPENID",
  "user_nickname": "用户昵称",
  "channel_id": "CHANNEL_ID",
  "group_id": "GUILD_ID",
  "message_id": "channel_msg_id_example",
  "message": [
    {
      "type": "mention",
      "data": {
        "user_id": "MENTIONED_USER_ID",
        "user_name": "被@用户昵称"
      }
    },
    {
      "type": "text",
      "data": {
        "text": "频道消息"
      }
    }
  ],
  "alt_message": "@被@用户昵称 频道消息"
}
```

### 4. 带图片的消息

原始事件:
```json
{
  "id": "msg_with_image",
  "author": {
    "member_openid": "MEMBER_OPENID"
  },
  "content": "看这个图片",
  "group_openid": "GROUP_OPENID",
  "timestamp": "2026-04-25T12:00:00+08:00",
  "attachments": [
    {
      "content_type": "image/png",
      "url": "https://multimedia.nt.qq.com/image_example.png"
    }
  ]
}
```

转换后:
```json
{
  "id": "msg_with_image",
  "time": 1745558400,
  "type": "message",
  "detail_type": "group",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "GROUP_AT_MESSAGE_CREATE",
  "user_id": "MEMBER_OPENID",
  "user_nickname": "",
  "group_id": "GROUP_OPENID",
  "message_id": "msg_with_image",
  "qqbot_group_openid": "GROUP_OPENID",
  "qqbot_member_openid": "MEMBER_OPENID",
  "qqbot_event_id": "msg_with_image",
  "qqbot_reply_token": "",
  "message": [
    {
      "type": "text",
      "data": {
        "text": "看这个图片"
      }
    },
    {
      "type": "image",
      "data": {
        "url": "https://multimedia.nt.qq.com/image_example.png",
        "qqbot_attachment": {
          "content_type": "image/png",
          "url": "https://multimedia.nt.qq.com/image_example.png"
        }
      }
    }
  ],
  "alt_message": "看这个图片 [图片]"
}
```

### 5. 群添加机器人事件（GROUP_ADD_ROBOT）

原始事件:
```json
{
  "timestamp": "2026-04-25T12:00:00+08:00",
  "group_openid": "GROUP_OPENID",
  "op_member_openid": "OPERATOR_OPENID"
}
```

转换后:
```json
{
  "id": "auto_generated_uuid",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "group_increase",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "GROUP_ADD_ROBOT",
  "group_id": "GROUP_OPENID",
  "operator_id": "OPERATOR_OPENID"
}
```

### 6. 好友添加事件（FRIEND_ADD）

原始事件:
```json
{
  "timestamp": "2026-04-25T12:00:00+08:00",
  "openid": "USER_OPENID"
}
```

转换后:
```json
{
  "id": "auto_generated_uuid",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "friend_add",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "FRIEND_ADD",
  "user_id": "USER_OPENID",
  "user_nickname": ""
}
```

### 7. 交互事件（INTERACTION_CREATE）

原始事件:
```json
{
  "id": "interaction_id",
  "type": "INTERACTION_TYPE",
  "data": {
    "resolved": {}
  },
  "timestamp": "2026-04-25T12:00:00+08:00"
}
```

转换后:
```json
{
  "id": "interaction_id",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "qqbot_interaction",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "INTERACTION_CREATE",
  "qqbot_interaction_id": "interaction_id",
  "qqbot_interaction_type": "INTERACTION_TYPE",
  "qqbot_interaction_data": {
    "resolved": {}
  }
}
```

### 8. 消息审核事件

审核通过（MESSAGE_AUDIT_PASS）:
```json
{
  "id": "audit_event_id",
  "audit_id": "AUDIT_ID",
  "message_id": "MESSAGE_ID",
  "timestamp": "2026-04-25T12:00:00+08:00"
}
```

转换后:
```json
{
  "id": "audit_event_id",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "qqbot_audit_pass",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "MESSAGE_AUDIT_PASS",
  "qqbot_audit_id": "AUDIT_ID",
  "qqbot_message_id": "MESSAGE_ID"
}
```

审核拒绝（MESSAGE_AUDIT_REJECT）:
```json
{
  "id": "audit_event_id",
  "audit_id": "AUDIT_ID",
  "message_id": "MESSAGE_ID",
  "audit_reject_reason": "内容违规",
  "timestamp": "2026-04-25T12:00:00+08:00"
}
```

转换后:
```json
{
  "id": "audit_event_id",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "qqbot_audit_reject",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "MESSAGE_AUDIT_REJECT",
  "qqbot_audit_id": "AUDIT_ID",
  "qqbot_message_id": "MESSAGE_ID",
  "qqbot_audit_reject_reason": "内容违规"
}
```

### 9. 频道成员变更事件

成员加入（GUILD_MEMBER_ADD）:
```json
{
  "guild_id": "GUILD_ID",
  "user": {
    "id": "USER_ID",
    "nick": "用户昵称"
  },
  "timestamp": "2026-04-25T12:00:00+08:00"
}
```

转换后:
```json
{
  "id": "auto_generated_uuid",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "guild_member_increase",
  "sub_type": "",
  "platform": "qqbot",
  "self": {
    "platform": "qqbot",
    "user_id": "BOT_APPID"
  },
  "qqbot_raw": {
    "...": "原始事件内容"
  },
  "qqbot_raw_type": "GUILD_MEMBER_ADD",
  "user_id": "USER_ID",
  "user_nickname": "用户昵称",
  "group_id": "GUILD_ID",
  "operator_id": ""
}
```

### 10. 群成员变更事件（v5 新增）

成员加入（GROUP_MEMBER_ADD，需订阅 GROUP_MEMBER intent）:
```json
{
  "group_openid": "GROUP_OPENID",
  "member_openid": "MEMBER_OPENID",
  "op_member_openid": "OPERATOR_OPENID",
  "timestamp": "1720000000000"
}
```

转换后:
```json
{
  "id": "auto_generated_uuid",
  "time": 1745558400,
  "type": "notice",
  "detail_type": "group_member_increase",
  "platform": "qqbot",
  "self": { "platform": "qqbot", "user_id": "BOT_APPID" },
  "qqbot_raw_type": "GROUP_MEMBER_ADD",
  "user_id": "MEMBER_OPENID",
  "group_id": "GROUP_OPENID",
  "operator_id": "OPERATOR_OPENID"
}
```

### 11. 入群申请事件（v5 新增，request）

原始事件（GROUP_JOIN_REQUEST）:
```json
{
  "join_request_id": "JOIN_REQUEST_ID",
  "group_openid": "GROUP_OPENID",
  "member_openid": "MEMBER_OPENID",
  "username": "申请人昵称",
  "apply_source": "self_apply",
  "verify_info": { "method": 1, "verify_message": "请通过" }
}
```

转换后:
```json
{
  "id": "auto_generated_uuid",
  "time": 1745558400,
  "type": "request",
  "detail_type": "group",
  "platform": "qqbot",
  "self": { "platform": "qqbot", "user_id": "BOT_APPID" },
  "qqbot_raw_type": "GROUP_JOIN_REQUEST",
  "request_id": "JOIN_REQUEST_ID",
  "user_id": "MEMBER_OPENID",
  "user_nickname": "申请人昵称",
  "group_id": "GROUP_OPENID",
  "comment": "请通过",
  "qqbot_join_request_id": "JOIN_REQUEST_ID",
  "qqbot_apply_source": "self_apply"
}
```

审批示例：
```python
from ErisPulse.Core.Event import request as request_event

@request_event.on_request()
async def handle_join(event):
    if event.get("platform") != "qqbot":
        return
    # 方式一：Event 便捷方法
    await event.approve()
    # await event.reject(comment="暂不通过")

    # 方式二：Request DSL
    # await qqbot.Request(event["request_id"]).accept()
    # await qqbot.Request(event["request_id"]).reject(comment="暂不通过")
```

---

## QQBot发送消息类型（OneBot12扩展）

QQBot适配器支持使用 OneBot12 消息段格式发送消息，支持以下类型：

### 1. 基础消息类型

| 类型 | 说明 | 参数 | msg_type |
|------|------|------|----------|
| `text` | 纯文本 | `text`: 文本内容 | 0 |
| `markdown` | Markdown格式 | `content`: Markdown内容 | 2 |
| `ark` | Ark模板消息 | `template_id`: 模板ID, `kv`: 键值对列表 | 3 |
| `embed` | Embed消息 | embed结构体数据 | 4 |

### 2. 媒体消息类型

| 类型 | 说明 | 参数 | msg_type |
|------|------|------|----------|
| `image` | 图片 | `file`: 文件路径/URL/bytes | 7 |
| `video` | 视频 | `file`: 文件路径/URL/bytes | 7 |
| `voice` | 语音 | `file`: 文件路径/URL/bytes | 7 |
| `file` | 文件 | `file`: 文件路径/URL/bytes | 7 |

> 媒体消息会先通过上传接口获取 `file_info`，然后以 msg_type=7 发送。

### 3. QQBot特有类型

| 类型 | 说明 | 参数 |
|------|------|------|
| `reply` | 回复消息 | `message_id`: 消息ID（通过链式修饰 `.Reply()` 设置） |
| `mention` | @用户 | `user_id`: 用户ID（通过链式修饰 `.At()` 设置） |

### 键盘消息

```python
keyboard = {
    "content": [
        [
            {"label": "按钮1", "type": 2, "data": "value1"},
            {"label": "按钮2", "type": 0, "data": "https://example.com"}
        ]
    ]
}

await qqbot.Send.To("group", group_id).Keyboard(keyboard).Text("带键盘的消息")
```

### 4. 使用链式调用发送

```python
from ErisPulse import sdk
qqbot = sdk.adapter.get("qqbot")

# 基础发送
await qqbot.Send.To("user", user_openid).Text("Hello")

# 发送带@的消息
await qqbot.Send.To("group", group_openid).At("member_openid").Text("@成员")

# 发送带按钮键盘的消息
await qqbot.Send.To("group", group_openid).Keyboard(keyboard).Text("请确认")

# 发送回复消息
await qqbot.Send.To("group", group_openid).Reply("msg_id").Text("回复内容")

# 发送Markdown消息
await qqbot.Send.To("group", group_openid).Markdown("# 标题\n内容")

# 发送Ark模板消息
await qqbot.Send.To("user", user_openid).Ark(template_id=1, kv=[{"key": "k", "value": "v"}])

# 发送Embed消息
await qqbot.Send.To("group", group_openid).Embed({"title": "标题", "content": "内容"})

# 使用 Raw_ob12 发送复杂消息
message = [
    {"type": "text", "data": {"text": "第一行"}},
    {"type": "image", "data": {"file": "https://example.com/img.jpg"}},
    {"type": "text", "data": {"text": "第二行"}}
]
await qqbot.Send.To("group", group_openid).Raw_ob12(message)
```

### 5. 发送目标类型

| target_type | 说明 | endpoint |
|-------------|------|----------|
| `user` | 私聊用户（openid） | `/v2/users/{target_id}/messages` |
| `group` | 群聊（group_openid） | `/v2/groups/{target_id}/messages` |
| `channel` | 频道 | `/channels/{target_id}/messages` |
| `dms` | 频道私信 | `/dms/{target_id}/messages` |

### 6. 媒体上传

发送图片、视频、语音、文件等媒体类型时，适配器会自动调用上传接口：

- 私聊：`POST /v2/users/{target_id}/files`
- 群聊：`POST /v2/groups/{target_id}/files`

支持的 `file_type` 参数：
| file_type | 类型 |
|-----------|------|
| 1 | 图片 |
| 2 | 视频 |
| 3 | 语音 |
| 4 | 文件 |

`file` 参数支持以下格式：
- `bytes`：二进制数据（自动base64编码）
- `str`（URL）：以 `http://` 或 `https://` 开头的网络地址
- `str`（本地路径）：本地文件路径

### 7. 消息回复机制

QQBot平台的群消息和私聊消息支持被动回复。适配器会自动管理回复所需的 `msg_id`：

- 收到消息时，适配器自动缓存 `message_id` 到 `_pending_msg_ids`
- 发送消息时，如果设置了 `.Reply(msg_id)`，会使用该ID作为回复引用
- 如果未显式设置 `.Reply()`，适配器会自动使用缓存的对应目标 `msg_id`

---

## OneBot12 标准API动作（v5 新增）

适配器实现了 ErisPulse `Api` DSL，模块可跨平台统一调用标准动作，适配器自动映射到QQ官方API并标准化 `data` 字段：

```python
qqbot = sdk.adapter.get("qqbot")

# 获取机器人信息 → GET /users/@me
result = await qqbot.Api.get_self_info()
print(result["data"]["user_id"], result["data"]["user_name"])

# 群信息 → GET /v2/groups/{id}/info
result = await qqbot.Api.get_group_info(group_openid)
print(result["data"]["group_name"])

# 群成员列表（自动分页聚合）→ GET /v2/groups/{id}/members
result = await qqbot.Api.get_group_member_list(group_openid)

# 频道信息 → GET /guilds/{id}
result = await qqbot.Api.get_guild_info(guild_id)

# 频道列表（多账户可用 Using 指定）
result = await qqbot.Api.Using("account2").get_guild_list()

# 子频道列表 → GET /guilds/{id}/channels
result = await qqbot.Api.get_channel_list(guild_id)

# 撤回消息（自动按消息来源路由到对应DELETE端点）
result = await qqbot.Api.delete_message(message_id)

# 元动作
result = await qqbot.Api.get_status()      # {good, bots: [...]}
result = await qqbot.Api.get_version()     # {impl, version, onebot_version}
result = await qqbot.Api.get_supported_actions()
```

**支持的标准动作**：`get_self_info` / `get_group_info` / `get_group_member_info` / `get_group_member_list` / `get_guild_info` / `get_guild_list` / `get_guild_member_info` / `get_guild_member_list` / `get_channel_info` / `get_channel_list` / `set_channel_name` / `leave_channel` / `delete_message` / `get_status` / `get_version` / `get_supported_actions`。

不支持的动作（如 `get_friend_list`、`set_group_name`）返回 `retcode=10002`。

平台扩展动作可直接传 REST 路径调用：

```python
# 自定义端点（默认 POST；_method 可覆盖HTTP方法）
result = await qqbot.call_api("/v2/groups/{group_openid}/info", _method="GET")
```

## 请求操作（Request DSL，v5 新增）

`GROUP_JOIN_REQUEST` 事件支持标准化审批：

```python
await qqbot.Request(request_id).accept()                    # 同意
await qqbot.Request(request_id).reject(comment="理由")      # 拒绝（附理由）
await qqbot.Request(request_id).Using("account2").accept()  # 指定账户
```

适配器会缓存事件中的申请上下文（群/申请人 openid），按 `request_id` 路由到 `POST /v2/groups/{group_openid}/approval_join_request/{member_openid}`。上下文过期或不存在时返回 `retcode=34001`。

---

## @机器人检测（重要）

**QQ官方的"被@"事实由事件名承载，而非消息内容**：`GROUP_AT_MESSAGE_CREATE` / `AT_MESSAGE_CREATE` 即表示用户@了机器人，`content` 中通常**没有**机器人自身的 @ 标记（`<qqbot-at-user>` 是发送方向专有格式）。

而 ErisPulse 框架的 `on_at_message()` / `event.is_at_message()` 依赖扫描消息段中 `user_id == self.user_id` 的 `mention` 段。因此适配器在转换"定义上就是@"的事件时，**保证注入机器人自身的 mention 段**：

| 场景 | 转换行为 |
|------|---------|
| GROUP_AT_MESSAGE_CREATE，content 无标记 | 前置注入 `{"type": "mention", "data": {"user_id": bot_id}}` |
| GROUP_AT_MESSAGE_CREATE，content 带 `<qqbot-at-user id="X">` | 首个标记归一为机器人（`user_id=bot_id`），原始群空间 openid 保留在 `data.qqbot_openid` |
| AT_MESSAGE_CREATE，content 无标记 | 同上注入（频道 id 空间与 bot_id 一致） |
| AT_MESSAGE_CREATE，content 带 `<@!BOT_ID>` | 已匹配，不重复注入 |
| GROUP_MESSAGE_CREATE（非@群消息） | 不注入，`qqbot_is_at_message=false` |
| C2C 私聊 | 不注入（私聊本身即定向对话） |

于是模块可以正常使用标准方式检测@：

```python
from ErisPulse.Core.Event import message

@message.on_at_message()
async def handle_at(event):
    # 群内@机器人的消息会触发到这里
    text = event.get_text()  # 纯文本（不含 @ 段）
    if text == "签到":
        await event.reply("已签到")

# 或手动检测
@message.on_message()
async def handle_msg(event):
    if event.is_at_message():
        pass
```
