# 部署

request-me 包含一个 QQ 请求中心和每台 Codex 主机各自运行的 MCP、Bridge。QQ 请求中心只有一个；每台主机使用独立 Bridge 身份和 token，MCP 与同机 Bridge 共享该身份。

## QQ 请求中心

安装 `server/requirements.txt`，从仓库根目录运行 `python -m server`。环境变量见 `server/.env.example`：

- `QQ_APPID`、`QQ_SECRET`：QQ Bot WebSocket 登录凭据。
- `REQUEST_ME_OWNER_OPENID`：人工请求的 QQ 接收者。
- `REQUEST_ME_BRIDGE_TOKENS`：`{"主机身份":"独立 token"}` 映射。
- `REQUEST_ME_HOST`、`REQUEST_ME_PORT`：HTTP 监听地址。

新增主机时，先为它生成不同于其他主机的 token，再同时更新服务端映射和该主机的私密配置。当前状态保存在内存中；重启前应先处理或关闭仍待回答的请求。

## Codex 主机

Node.js 20 及以上版本中构建：

```sh
npm ci
npm run build
```

复制 `config/bridge.example.json` 为不纳入版本控制的本地配置。`token_env` 指定的环境变量必须包含该主机自己的 token。`codex_binary` 应指向支持 `codex queue` 的实际 Codex CLI；配置远端 Codex app-server 时填写 `app_server_url`，本机默认路由可以留空。

MCP 和 Bridge 使用同一配置，但分别运行：

```sh
node /absolute/path/request-me/dist/bin/request-me-mcp.js --config /absolute/path/bridge.local.json
node /absolute/path/request-me/dist/bin/request-me-bridge.js --config /absolute/path/bridge.local.json
```

Bridge 应由 systemd、Windows 服务管理器或任务计划程序常驻管理，并设置失败重启。只运行一个使用同一身份的 Bridge 实例，避免多个消费者竞争回答。

## 注册 MCP

按照[官方 Codex MCP 文档](https://developers.openai.com/codex/mcp)，STDIO MCP 可以通过 CLI 注册：

```sh
codex mcp add request_me -- node /absolute/path/request-me/dist/bin/request-me-mcp.js --config /absolute/path/bridge.local.json
```

token 可以由进程环境、服务管理器或本机私密启动器提供。不要把 token 写入仓库配置示例。Codex Desktop、CLI 与 IDE 在同一主机共享 MCP 配置；修改后重启对应客户端或重新加载 MCP 工具清单。

## 验收

部署后按顺序确认：

1. QQ Bot 已连接，请求中心端口可达。
2. Bridge 持续进行 `/v1/answers?wait=25` 长轮询且没有反复重启。
3. MCP 的 `tools/list` 包含 `request_user_response`、`send_user_notification`、`close_user_request`。
4. 用真实 Codex 任务发起一个按钮请求，点击后确认回答进入同一任务的队列。
5. 重复点击不会产生第二条回答；成功投递不产生额外 QQ 回执气泡。
