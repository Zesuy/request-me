# request-me

通过 QQ 将人接入 Codex 的异步工作流程：Agent 交代进展和需要人参与的原因，结束当前轮；用户回答后，由 Bridge 将输入送回原会话继续工作。

一个仓库维护 QQ 服务端、MCP 和 Bridge，分别部署。一个 QQ 服务端接收多个 Bridge、多个 Codex 会话的人工请求。MCP 与 Bridge 由同一个 Node.js 包提供，QQ 接入使用 Python/NoneBot。

下一次继续工作，请先读 [设计与实施说明](docs/DESIGN.md)，其中包含用户原话、交互语义、部署关系和近期验收目标。

核心实现已包括 Node.js MCP、Node.js Bridge 和 Python/NoneBot QQ 服务端。首版范围为 Codex 与 QQ 的人工交互，以及附带的通知能力；原型保存在相邻的 `nonebot-prototype/`。

外部应用通过[配置化 HTTP 接入](docs/APPLICATIONS.md)处理 QQ 命令和操作卡片。应用在独立仓库维护业务调用与呈现，Bot 按配置转发命令、保存按钮回程并转换 QQ 消息。

## 运行

Node.js 20 及以上版本中安装依赖并构建：

```sh
npm ci
npm run build
```

当前仓库可直接运行：

```sh
node /absolute/path/request-me/dist/bin/request-me-mcp.js --config /absolute/path/bridge.local.json
node /absolute/path/request-me/dist/bin/request-me-bridge.js --config /absolute/path/bridge.local.json
```

发布为 npm 包后，全局安装会提供 `request-me-mcp` 和 `request-me-bridge` 两个命令。它们共享实现与配置，但仍是独立进程：MCP 由 Codex 按需启动，Bridge 在同一主机常驻。

服务端安装 `server/requirements.txt`，按 `server/.env.example` 配置环境变量，从仓库根目录执行 `python -m server`。QQ AppID 与 AppSecret 用于 WebSocket 登录；owner openid 是消息接收目标，每个 Bridge 使用独立 token。

MCP 与 Bridge 共享 `config/bridge.example.json` 格式的配置。设置其中 `token_env` 指定的环境变量，将 MCP 命令及 `--config /absolute/path/bridge.local.json` 注册到 Codex；在同一执行主机常驻运行 Bridge，使用对应 Codex 的 app-server 地址。为兼容已有部署，`-config` 也继续可用。

开发检查使用 `npm test`；如需同时验证 Python 请求中心与 Node Bridge 契约，设置 `REQUEST_ME_TEST_PYTHON` 为已安装服务端依赖的 Python 可执行文件后再运行测试。

[协议说明](docs/PROTOCOL.md)记录发送、回程、关闭和回执。当前状态保存在内存中，重启恢复尚未实现。开发验收优先使用真实 QQ 与持久 Codex 任务，离线测试作为补充。

正式安装和双端配置见[部署说明](docs/DEPLOYMENT.md)。
