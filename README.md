<div align="center">

<img src=".github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse QQBotAdapter" />

# ErisPulse QQBotAdapter

**QQ 官方机器人平台适配器 —— 群聊 / 私聊 / 频道一站接入。**

基于 ErisPulse 架构的 QQ 官方机器人协议适配器，支持 WebSocket / Webhook 双接入模式与多账户并行，整合群聊、私聊、频道等场景，提供 OneBot12 标准事件、标准Api动作与请求操作接口。

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

QQBotAdapter 是基于 [ErisPulse](https://github.com/ErisPulse/ErisPulse/) 架构的QQ官方机器人协议适配器，整合群聊、私聊、频道等多种场景的功能模块，提供统一的事件处理和消息操作接口。

**v5.0 亮点：**
- 🌐 对齐官方最新 API：统一域名 `api.bot.qq.com`、新增 `X-Union-Appid` 头、sandbox 废弃
- 🔌 **双接入模式**：WebSocket 长连接 / Webhook HTTP 回调（Ed25519 验签）
- 👥 **多账户并行**：每账户独立连接与 token 管理，`Using()` 灵活切换
- 📡 **OneBot12 标准Api动作**：`Api.get_group_info()` / `Api.delete_message()` 等跨平台统一调用
- 🤝 **请求操作**：入群申请（GROUP_JOIN_REQUEST）标准化 `accept()/reject()` 审批
- 🚀 **流式消息**：单聊流式输出（stream_messages）
- 📦 全量平台API方法族：群管理、菜单面板、日程、帖子、表态、分片上传等

## 平台原生事件映射关系

| 官方事件命名 | Adapter事件命名 |
|--------------|----------------|
| C2C_MESSAGE_CREATE | private_message |
| GROUP_AT_MESSAGE_CREATE | group_message |
| GROUP_MESSAGE_CREATE | group_message（非@群消息，需后台开通接收全部消息权限） |
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
| GROUP_MEMBER_ADD | group_member_add（v5新增） |
| GROUP_MEMBER_REMOVE | group_member_remove（v5新增） |
| GROUP_JOIN_REQUEST | group_join_request（v5新增，request事件） |
| GUILD_MEMBER_ADD | guild_member_add |
| GUILD_MEMBER_UPDATE | guild_member_update |
| GUILD_MEMBER_REMOVE | guild_member_remove |
| INTERACTION_CREATE | interaction |
| MESSAGE_AUDIT_PASS | audit_pass |
| MESSAGE_AUDIT_REJECT | audit_reject |

这仅仅在 `sdk.adapter.qqbot.on()` 的时候生效，你完全可以使用标准OneBot12事件（`sdk.adapter.on`）来获取信息。

### OneBot12标准事件类型

| 事件类型 | detail_type | 说明 |
|----------|-------------|------|
| 消息事件（私聊） | private | 用户发送的私聊消息 |
| 消息事件（群聊） | group | 群内消息（@或非@） |
| 消息事件（频道） | channel | 频道内消息 |
| 请求事件（入群申请） | group | **type=request**，含 request_id，支持审批 |
| 好友增加/删除 | friend_add / friend_del | 用户添加/删除机器人好友 |
| 群增加/减少 | group_increase / group_decrease | 群添加/移除机器人 |
| 群消息屏蔽/允许 | group_block / group_allow | 群拒绝/允许机器人消息 |
| 私聊屏蔽/允许 | private_block / private_allow | 用户拒绝/允许机器人私聊 |
| 群成员增加/减少 | group_member_increase / group_member_decrease | **群**成员变更（v5新增） |
| 频道成员增加/更新/减少 | guild_member_increase / guild_member_update / guild_member_decrease | **频道**成员变更 |
| 频道服务器创建/更新/删除 | guild_create / guild_update / guild_delete | 频道服务器变更 |
| 子频道创建/更新/删除 | channel_create / channel_update / channel_delete | 子频道变更 |
| 音频子频道进出 | qqbot_channel_enter / qqbot_channel_exit | 用户进入/离开音频直播子频道（v5新增） |
| QQBot交互事件 | qqbot_interaction | 按钮点击等交互 |
| QQBot审核通过/拒绝 | qqbot_audit_pass / qqbot_audit_reject | 消息审核结果 |
| QQBot表情回应添加/移除 | qqbot_reaction_add / qqbot_reaction_remove | 消息表情回应 |
| QQBot音频开始/结束 | qqbot_audio_start / qqbot_audio_finish | 音频播放 |
| QQBot消息删除 | qqbot_message_delete | 消息被删除 |
| QQBot论坛事件 | qqbot_forum_* | 论坛主帖/帖子/回复/审核（私域） |

---

## 消息发送示例

```python
from ErisPulse import sdk
qqbot = sdk.adapter.get("qqbot")

# 发送文本消息
await qqbot.Send.To("user", user_openid).Text("Hello World!")

# 发送带@的消息（群/私聊自动使用 qqbot-at-user 格式）
await qqbot.Send.To("group", group_openid).At("member_openid").Text("@你")
await qqbot.Send.To("group", group_openid).AtAll().Text("公告通知")

# 发送回复消息（被动回复）
await qqbot.Send.To("group", group_openid).Reply("msg_id").Text("回复内容")

# 发送图片（URL / 本地路径 / 二进制三态；超过5MB自动分片上传）
await qqbot.Send.To("group", group_openid).Image("https://example.com/image.png")

# 发送 Markdown（原生 / 模板）
await qqbot.Send.To("group", group_openid).Markdown("# 标题\n- 列表项")
await qqbot.Send.To("user", user_openid).Markdown(template_id=1, kv=[{"key": "title", "value": "通知"}])

# 发送 Ark 模板消息
await qqbot.Send.To("user", user_openid).Ark(template_id=1, kv=[{"key": "title", "value": "标题"}])

# 发送 Embed 消息（频道）
await qqbot.Send.To("channel", channel_id).Embed({"title": "标题", "content": "内容"})

# 发送带键盘的消息（自动置为 markdown 类型并附带 bot_appid）
keyboard = {"content": {"rows": [[{"label": "确认", "type": 2, "data": "confirm"}]]}}
await qqbot.Send.To("group", group_openid).Keyboard(keyboard).Text("请选择")

# 流式消息（单聊）
await qqbot.Send.To("user", user_openid).Stream("回答内容")

# 多账户
await qqbot.Send.Using("account2").To("group", group_openid).Text("来自第二个机器人")

# 使用 Raw_ob12 发送 OneBot12 格式消息
message = [
    {"type": "text", "data": {"text": "第一行"}},
    {"type": "image", "data": {"file": "https://example.com/img.jpg"}},
]
await qqbot.Send.To("group", group_openid).Raw_ob12(message)
```

---

## 标准Api动作与请求操作（v5 新增）

```python
# OneBot12 标准Api动作（跨平台统一调用）
result = await qqbot.Api.get_self_info()                     # 机器人信息
result = await qqbot.Api.get_group_info(group_openid)        # 群信息
result = await qqbot.Api.get_group_member_list(group_openid) # 群成员列表（自动分页）
result = await qqbot.Api.get_guild_list()                    # 频道列表
result = await qqbot.Api.get_channel_list(guild_id)          # 子频道列表
await qqbot.Api.delete_message(message_id)                   # 撤回消息（自动路由端点）
result = await qqbot.Api.get_status()                        # 运行状态

# 请求操作：入群申请审批
from ErisPulse.Core.Event import request as request_event

@request_event.on_request()
async def handle_join(event):
    if event.get("platform") == "qqbot":
        await event.approve()                     # 同意
        # await event.reject(comment="理由")      # 拒绝
```

---

### 配置说明

首次运行会自动生成默认配置。

```toml
# config.toml
[QQBot_Adapter]
intents = "[0, 9, 12, 25, 26, 27]"    # 订阅的事件 intents（JSON数组，支持事件名）

[QQBot_Adapter.accounts.default]
appid = "YOUR_APPID"                  # QQ机器人应用ID（必填）
secret = "YOUR_CLIENT_SECRET"         # QQ机器人客户端密钥（必填）
mode = "websocket"                    # websocket / webhook
bot_id = ""                           # 留空自动获取（可手动填写用于 Using() 定位）
gateway_url = ""                      # WebSocket网关（留空动态获取）
api_base_url = "https://api.bot.qq.com"
webhook_path = "/webhook"             # mode=webhook 时生效
enabled = true
```

**配置项说明：**
- `appid` / `secret`：从 [QQ开放平台](https://q.qq.com/) 获取（必填）
- `mode`：事件接收方式，`websocket`（默认，长连接）或 `webhook`（HTTP 回调 + Ed25519 验签）
- `intents`：事件订阅，支持位序号或事件名，常用：`0` 频道 / `9,30` 频道消息 / `12` 频道私信 / `24` 群成员 / `25` 群私聊 / `26` 交互 / `27` 审核
- `gateway_url`：WebSocket 网关地址，留空时通过 `/gateway/bot` 动态获取（支持代理/私有部署）
- `api_base_url`：OpenAPI 根地址，默认 `https://api.bot.qq.com`
- 多账户：在 `accounts` 下添加多个账户即可并行接入（可混合 websocket/webhook 模式）

> ⚠️ **v5 破坏性变更**：官方已统一使用 `api.bot.qq.com`，`sandbox` 配置废弃（自动迁移忽略）；旧版扁平配置自动迁移到 `accounts.default`。

---

## QQBot平台特有功能

请参考 [QQBot平台特性文档](platform-features.md) 了解QQBot平台的特有功能，包括openid体系、频道系统、群管理API、菜单面板、流式消息、消息审核、交互事件、Webhook接入等内容。

详细的事件转换对照请参考 [转换对照文档](CoverToOnebot12.md)。

## 事件监听示例

### 使用 Event 模块（推荐）

```python
from ErisPulse.Core.Event import message, notice, request

# @消息（群内@机器人触发，适配器自动注入机器人 mention 段）
@message.on_at_message()
async def handle_at(event):
    if event["platform"] == "qqbot":
        text = event.get_text()
        if text == "签到":
            await event.reply("已签到")

@message.on_message()
async def handle_message(event):
    if event["platform"] == "qqbot":
        detail_type = event["detail_type"]
        if detail_type == "private":
            pass  # 处理私聊消息
        elif detail_type == "group":
            pass  # 处理群消息
        elif detail_type == "channel":
            pass  # 处理频道消息

@notice.on_notice()
async def handle_notice(event):
    if event["platform"] == "qqbot":
        detail_type = event["detail_type"]
        if detail_type == "qqbot_interaction":
            button_id = event.get("qqbot_button_id", "")

@request.on_request()
async def handle_request(event):
    if event["platform"] == "qqbot":
        await event.approve()  # 自动审批入群申请
```

### 使用平台原生事件

```python
qqbot = sdk.adapter.get("qqbot")

@qqbot.on("C2C_MESSAGE_CREATE")
async def handle_private_message(data):
    pass

@qqbot.on("GROUP_JOIN_REQUEST")
async def handle_join_request(data):
    pass
```

### 使用 OneBot12 标准事件

```python
@sdk.adapter.on("message")
async def handle_message(event):
    if event["platform"] == "qqbot":
        bot_id = event["self"]["user_id"]
        print(f"消息来自Bot: {bot_id}")
```

## 注意事项：

1. 确保在调用 `startup()` 前完成所有处理器的注册
2. QQBot使用 openid 体系而非QQ号，用户和群的标识均为 openid 字符串
3. 群消息默认仅在用户@机器人时才会收到（`GROUP_AT_MESSAGE_CREATE`）；如需接收全部群消息，请在 [QQ开放平台](https://q.qq.com/) 机器人管理后台开启权限（无API），非@消息将以 `GROUP_MESSAGE_CREATE` 推送
4. **@检测已支持**：适配器自动为@消息注入机器人 mention 段，`on_at_message()`/`event.is_at_message()` 可直接使用；群空间原始 openid 保留在 mention 段 `data.qqbot_openid`
5. 发送的消息可能需要经过审核，通过 `qqbot_audit_pass`/`qqbot_audit_reject` 事件通知结果
6. 媒体文件（图片、视频等）会上传后通过 file_info 发送，支持URL、本地路径和二进制数据；超过5MB自动分片上传
7. 程序退出时请调用 `shutdown()` 确保资源释放
8. access_token 有效期为7200秒，适配器提前45秒自动刷新
9. 群管理部分API（成员列表、入群审批等）仅对白名单机器人开放

---

### 参考链接

- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)
- [QQBot 官方文档](https://bot.q.qq.com/wiki/)
- [模块开发指南](https://www.erisdev.com/#docs/developer-guide/README.md)
