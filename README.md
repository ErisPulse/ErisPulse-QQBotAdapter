<div align="center">

<img src=".github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse QQBotAdapter" />

# ErisPulse QQBotAdapter

**QQ 官方机器人平台适配器 —— 群聊 / 私聊 / 频道一站接入。**

基于 ErisPulse 架构的 QQ 官方机器人协议适配器，通过 WebSocket 长连接接收事件，整合群聊、私聊、频道等多种场景，提供统一的事件处理和消息操作接口。

<p>
  <a href="https://pypi.org/project/ErisPulse-QQBotAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-QQBotAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-QQBotAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <a href="https://github.com/ErisPulse/ErisPulse-QQBotAdapter"><img src="https://img.shields.io/github/stars/ErisPulse/ErisPulse-QQBotAdapter?style=for-the-badge&logo=github&color=brightgreen" alt="Stars"></a>
  <a href="https://pepy.tech/project/ErisPulse-QQBotAdapter"><img src="https://img.shields.io/pepy/dt/ErisPulse-QQBotAdapter?style=for-the-badge&color=blue" alt="Downloads"></a>
  <a href="https://github.com/ErisPulse/ErisPulse"><img src="https://img.shields.io/badge/Powered_by-ErisPulse-FF6B9D?style=for-the-badge&logo=bookstack&logoColor=white" alt="ErisPulse"></a>
</p>

</div>

---

## 简介
QQBotAdapter 是基于 [ErisPulse](https://github.com/ErisPulse/ErisPulse/) 架构的QQ官方机器人协议适配器，通过WebSocket长连接接收事件，整合了群聊、私聊、频道等多种场景的功能模块，提供统一的事件处理和消息操作接口。

## 使用示例

### 平台原生事件映射关系
| 官方事件命名 | Adapter事件命名 |
|--------------|----------------|
| C2C_MESSAGE_CREATE | private_message |
| GROUP_AT_MESSAGE_CREATE | group_message |
| AT_MESSAGE_CREATE | channel_message |
| MESSAGE_CREATE | channel_message |
| DIRECT_MESSAGE_CREATE | direct_message |
| FRIEND_ADD | friend_add |
| FRIEND_DEL | friend_del |
| GROUP_ADD_ROBOT | group_add |
| GROUP_DEL_ROBOT | group_del |
| GROUP_MSG_REJECT | group_block |
| GROUP_MSG_RECEIVE | group_allow |
| C2C_MSG_REJECT | private_block |
| C2C_MSG_RECEIVE | private_allow |
| GUILD_MEMBER_ADD | guild_member_add |
| GUILD_MEMBER_UPDATE | guild_member_update |
| GUILD_MEMBER_REMOVE | guild_member_remove |
| INTERACTION_CREATE | interaction |
| MESSAGE_AUDIT_PASS | audit_pass |
| MESSAGE_AUDIT_REJECT | audit_reject |

这仅仅在 `sdk.adapter.qqbot.on()` 的时候生效，你完全可以使用标准OneBot12事件（`sdk.adapter.on`）来获取信息。

### OneBot12标准事件类型

QQBot适配器完全兼容 OneBot12 标准事件格式，并提供了一些扩展字段：

| 事件类型 | detail_type | 说明 |
|----------|-------------|------|
| 消息事件（私聊） | private | 用户发送的私聊消息 |
| 消息事件（群聊） | group | 群内用户@机器人的消息 |
| 消息事件（频道） | channel | 频道内消息 |
| 好友增加 | friend_add | 用户添加机器人为好友 |
| 好友删除 | friend_del | 用户删除机器人好友 |
| 群增加 | group_increase | 群添加机器人 |
| 群减少 | group_decrease | 群移除机器人 |
| 群消息屏蔽 | group_block | 群拒绝机器人消息 |
| 群消息允许 | group_allow | 群允许机器人消息 |
| 私聊屏蔽 | private_block | 用户拒绝机器人私聊 |
| 私聊允许 | private_allow | 用户允许机器人私聊 |
| 群成员增加 | group_member_increase | 频道成员加入 |
| 群成员更新 | group_member_update | 频道成员更新 |
| 群成员减少 | group_member_decrease | 频道成员退出 |
| 频道服务器创建 | guild_create | 频道服务器创建 |
| 频道服务器更新 | guild_update | 频道服务器更新 |
| 频道服务器删除 | guild_delete | 频道服务器删除 |
| 子频道创建 | channel_create | 子频道创建 |
| 子频道更新 | channel_update | 子频道更新 |
| 子频道删除 | channel_delete | 子频道删除 |
| QQBot交互事件 | qqbot_interaction | 按钮点击等交互 |
| QQBot审核通过 | qqbot_audit_pass | 消息审核通过 |
| QQBot审核拒绝 | qqbot_audit_reject | 消息审核拒绝 |
| QQBot表情回应添加 | qqbot_reaction_add | 消息表情回应添加 |
| QQBot表情回应移除 | qqbot_reaction_remove | 消息表情回应移除 |
| QQBot音频开始 | qqbot_audio_start | 音频开始播放 |
| QQBot音频结束 | qqbot_audio_finish | 音频播放结束 |
| QQBot消息删除 | qqbot_message_delete | 消息被删除 |

---

## 消息发送示例

```python
from ErisPulse import sdk
qqbot = sdk.adapter.get("qqbot")

# 发送文本消息
await qqbot.Send.To("user", user_openid).Text("Hello World!")

# 发送带@的消息
await qqbot.Send.To("group", group_openid).At("member_openid").Text("@你")

# 发送带@所有人的消息
await qqbot.Send.To("group", group_openid).AtAll().Text("公告通知")

# 发送回复消息
await qqbot.Send.To("group", group_openid).Reply("msg_id").Text("回复内容")

# 发送图片（URL）
await qqbot.Send.To("group", group_openid).Image("https://example.com/image.png")

# 发送图片（二进制数据）
with open("image.png", "rb") as f:
    image_data = f.read()
await qqbot.Send.To("user", user_openid).Image(image_data)

# 发送 Markdown 格式消息
await qqbot.Send.To("group", group_openid).Markdown("# 标题\n- 列表项")

# 发送 Ark 模板消息
await qqbot.Send.To("user", user_openid).Ark(template_id=1, kv=[{"key": "title", "value": "标题"}])

# 发送 Embed 消息
await qqbot.Send.To("group", group_openid).Embed({"title": "标题", "content": "内容"})

# 发送带键盘的消息
keyboard = {
    "content": [
        [
            {"label": "确认", "type": 2, "data": "confirm"},
            {"label": "取消", "type": 2, "data": "cancel"}
        ]
    ]
}
await qqbot.Send.To("group", group_openid).Keyboard(keyboard).Text("请选择")

# 组合使用：回复 + @ + 键盘
await qqbot.Send.To("group", group_openid).Reply("msg_id").At("member_openid").Keyboard(keyboard).Text("复合消息")

# 使用 Raw_ob12 发送 OneBot12 格式消息
message = [
    {"type": "text", "data": {"text": "第一行"}},
    {"type": "image", "data": {"file": "https://example.com/img.jpg"}},
    {"type": "text", "data": {"text": "第二行"}}
]
await qqbot.Send.To("group", group_openid).Raw_ob12(message)
```

---

### 配置说明

首次运行会自动生成默认配置。

```toml
# config.toml
[QQBot_Adapter]
appid = "YOUR_APPID"                                    # QQ机器人应用ID（必填）
secret = "YOUR_CLIENT_SECRET"                            # QQ机器人客户端密钥（必填）
sandbox = false                                          # 是否使用沙盒环境（可选，默认为false）
intents = [1, 30, 25]                                    # 订阅的事件 intents 位（可选）
gateway_url = "wss://api.sgroup.qq.com/websocket/"       # WebSocket网关地址（可选）
```

**配置项说明：**
- `appid`：QQ机器人的应用ID（必填），从QQ开放平台获取
- `secret`：QQ机器人的客户端密钥（必填），从QQ开放平台获取
- `sandbox`：是否使用沙盒环境，沙盒环境API地址为 `https://sandbox.api.sgroup.qq.com`
- `intents`：事件订阅 intents 列表，常用值：
  - `1`：频道相关事件
  - `25`：频道消息事件
  - `30`：群@消息事件
- `gateway_url`：WebSocket 网关地址，默认为 `wss://api.sgroup.qq.com/websocket/`

---

## QQBot平台特有功能

请参考 [QQBot平台特性文档](platform-features.md) 了解QQBot平台的特有功能，包括openid体系、频道系统、消息审核、交互事件、扩展字段说明等内容。

详细的事件转换对照请参考 [转换对照文档](CoverToOnebot12.md)。

## 事件监听示例

### 使用 Event 模块（推荐）

```python
from ErisPulse.Core.Event import message, notice

@message.on_message()
async def handle_message(event):
    if event["platform"] == "qqbot":
        detail_type = event["detail_type"]
        if detail_type == "private":
            # 处理私聊消息
            pass
        elif detail_type == "group":
            # 处理群@消息
            pass
        elif detail_type == "channel":
            # 处理频道消息
            pass

@notice.on_notice()
async def handle_notice(event):
    if event["platform"] == "qqbot":
        detail_type = event["detail_type"]
        if detail_type == "qqbot_interaction":
            # 处理交互事件（按钮点击等）
            interaction_id = event.get("qqbot_interaction_id", "")
        elif detail_type == "qqbot_audit_pass":
            # 消息审核通过
            pass
        elif detail_type == "qqbot_audit_reject":
            # 消息审核拒绝
            reason = event.get("qqbot_audit_reject_reason", "")
```

### 使用平台原生事件

```python
qqbot = sdk.adapter.get("qqbot")

# 使用平台原始事件名
@qqbot.on("C2C_MESSAGE_CREATE")
async def handle_private_message(data):
    pass

@qqbot.on("GROUP_AT_MESSAGE_CREATE")
async def handle_group_message(data):
    pass

@qqbot.on("INTERACTION_CREATE")
async def handle_interaction(data):
    pass
```

### 使用 OneBot12 标准事件

```python
@sdk.adapter.on("message")
async def handle_message(event):
    if event["platform"] == "qqbot":
        bot_id = event["self"]["user_id"]
        print(f"消息来自Bot: {bot_id}")

@sdk.adapter.on("notice")
async def handle_notice(event):
    if event["platform"] == "qqbot":
        # 处理QQBot通知事件
        pass
```

## 注意事项：

1. 确保在调用 `startup()` 前完成所有处理器的注册
2. QQBot使用 openid 体系而非QQ号，用户和群的标识均为 openid 字符串
3. 群消息仅在用户@机器人时才会收到（`GROUP_AT_MESSAGE_CREATE`）
4. 发送的消息可能需要经过审核，通过 `qqbot_audit_pass`/`qqbot_audit_reject` 事件通知结果
5. 媒体文件（图片、视频等）会上传后通过 file_info 发送，支持URL、本地路径和二进制数据
6. 程序退出时请调用 `shutdown()` 确保资源释放
7. access_token 有效期为7200秒，适配器会自动刷新

---

### 参考链接

- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)
- [QQBot 官方文档](https://bot.q.qq.com/wiki/)
- [模块开发指南](https://www.erisdev.com/#docs/developer-guide/README.md)
