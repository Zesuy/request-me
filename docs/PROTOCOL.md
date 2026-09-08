# HTTP 协议 v1

MCP 对外工具为 `send_user_notification`、`request_user_response`、`close_user_request`，投递渠道由服务端配置。通知发送后继续工作；需要用户参与时发起请求，收到发送回执后交接本轮。工具更名保持下面的 HTTP 路径与请求 ID 生成规则不变。

服务端根据 `Authorization: Bearer <token>` 确认 Bridge 身份。模型仅提供正文、选项和需关闭的请求 ID；MCP 从逐次调用元数据取得具体 Codex thread ID。配置中的 app-server 地址决定对应 Codex 主机。

## 发送

`POST /v1/requests`：

```json
{
  "id": "由MCP生成的请求ID",
  "thread_id": "具体Codex任务UUID",
  "markdown": "配置已完成，但设备仍然离线。请重新插拔，完成后我会检查。",
  "options": [
    {"id": "recheck", "label": "已重新连接", "value": "我已重新连接设备，请再次检查"},
    {"id": "stop", "label": "结束这项工作", "value": "请结束这项工作"}
  ],
  "source": {"title": "检查设备连接", "cwd": "/work/tmp", "host": "WSL"}
}
```

QQ 接受后返回 `{"id":"…","status":"sent","message_id":"…"}`。MCP 随即返回，Agent 结束本轮。选项最多 8 个；人工输入和关闭按钮由 QQ 层附加。人工输入预填 `/respond <短码> `，短码在送给 Codex 前去除。

`POST /v1/notifications` 使用相同结构，省略 `options`，返回相同发送回执。通知不创建待答问题。

幂等范围是 Bridge + id；重复内容沿用首次发送结果，正文、路由或类型冲突返回 409。来源补全变化不导致重复发送。发送结果不确定时保留记录并拒绝隐式重发。

## 回答与关闭

QQ 回调携带服务端生成的短码与选项 ID，服务端查找原请求及选项值。短码全局唯一，同一客户端 ID 可在不同 Bridge 使用。首个有效答案生效；后续提交提示已处理。

`GET /v1/answers?wait=25` 按 Bridge 长轮询，最多等待 25 秒：

```json
{"answers":[{"id":"回答UUID","request_id":"原请求ID","thread_id":"具体任务UUID","text":"我已重新连接设备，请再次检查"}]}
```

Bridge 将请求 ID 和回答正文作为原任务的新用户输入交给 `codex queue`；请求 ID 使同一任务的多个问题也能区分。通过 `POST /v1/answers/{id}/receipt` 回报：

```json
{"status":"accepted","detail":"codex queue accepted the input"}
```

- `accepted`：queue 进程成功退出，输入已被接收。
- `failed`：参数无效或 queue 进程未能启动。
- `unknown`：queue 已启动，但超时、中断或非零退出，是否入队待核对。

回执与 Agent 的后续进展分开。按钮的“已提交”表示回答已进入收件箱；成功投递仅记录内部回执，不产生聊天气泡。失败或结果不确定时才发送异常通知。Agent 使用 `send_user_notification` 提供实际进展、结果或新发现。

`POST /v1/requests/{id}/close`，正文 `{"thread_id":"原任务UUID"}`。所属 Bridge 与任务匹配且仍待答时关闭；QQ 也可通过关闭按钮执行。关闭不创建新用户输入。`close_user_request` MCP 用于在桌面已经解决问题时收起旧请求。

## 本阶段边界

单进程 QQ 服务端，单个 owner C2C 目标，多 Bridge。路由表和领取记录在内存中；每个答案领取一次。Bridge 在当前进程内去重并重试回执，结果不确定的 queue 调用不自动重放。网络中断丢失领取响应或进程重启后的恢复、待答列表及人工重投界面留作后续迭代。

调用元数据使用 `threadId` 或 `x-codex-turn-metadata.thread_id`，两个具体 ID 冲突时报错；`session_id` 不用于分支回程。配置 app-server 后，以只读 `thread/read` 补充标题和目录；缺少或读取失败时只显示可确认的主机名。
