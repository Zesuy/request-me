# HTTP 应用接入 v1

QQ 中心按配置转发主人单聊的命令，应用返回 Markdown 与操作卡片。业务 API、状态解释、按钮选择和文本组织由应用维护。增加应用只需部署接入端、配置命令与凭据。

设置 `REQUEST_ME_APPLICATIONS_FILE=/config/applications.json`，文件格式见 `config/applications.example.json`。每项指定唯一 `id`、完整命令首词 `command`、固定 `endpoint`、`token_env` 和请求超时秒数 `timeout`（默认 100，最大 300）。应用凭据从该环境变量读取。修改配置后重启 QQ 中心。

例如 `/example status` 匹配 `/example`，`/example-other` 不匹配；`/respond` 保留给人工回答。仅 owner C2C 消息和点击可触发应用。中心只 POST 到配置中的地址，不跟随重定向。请求头为 `Authorization: Bearer <应用凭据>`，接入端校验该凭据。

命令事件：

```json
{"version":1,"id":"QQ消息ID","kind":"command","user_id":"owner openid","text":"status"}
```

应用在同一次 HTTP 请求中以 200 返回卡片：

```json
{
  "markdown":"**设备空闲**\n\n可以开始操作。",
  "actions":[{"id":"start","label":"开始","value":{"operation":"start"}}],
  "context":{"device":"example"}
}
```

`markdown` 原样进入 QQ 渲染层；`actions` 最多 8 个，ID 唯一，每行 2 个。`value` 和 `context` 为应用自定义 JSON 对象。无按钮时返回空列表。卡片没有人工请求的标题、自由回复或关闭按钮。

QQ 回调只携带中心生成的卡片短码与 action ID。中心查找保存的应用、按钮和上下文，先确认点击，再 POST 到同一个应用地址：

```json
{"version":1,"id":"QQ交互ID","kind":"action","user_id":"owner openid","action":{"id":"start","label":"开始","value":{"operation":"start"}},"context":{"device":"example"}}
```

接入端执行后返回下一张卡片。每张卡片只接受首次有效操作，后续使用新卡片；这用于操作去重，不代表设备状态。用户可重新发送命令。命令事件按 QQ 消息 ID 去重，应用也应按事件 ID 去重；新的用户命令使用新 ID。

应用的业务失败仍返回 HTTP 200 卡片，说明失败原因和可用操作。超时、HTTP 错误和无效卡片由中心提示结果未确认，不自动重放。应用需要自行设置下游超时，使其小于配置的整体 timeout。QQ 发送失败写入日志，不重复执行业务。

卡片、事件去重记录只保存在内存，24 小时过期。重启后旧卡片失效，可重新发送命令。Codex `/v1/requests`、`/v1/notifications` 与回答长轮询保持原协议；应用操作卡片使用单独回程，与 Codex 会话无关。
