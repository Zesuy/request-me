# request-me

通过 QQ 将人接入 Codex 的异步工作流程：Agent 交代进展和需要人参与的原因，结束当前轮；用户回答后，由 Bridge 将输入送回原会话继续工作。

一个仓库维护 QQ 服务端、MCP 和 Bridge，分别构建、部署。一个 QQ 服务端接收多个 Bridge、多个 Codex 会话的人工请求。MCP 与 Bridge 使用 Go，QQ 接入参考现有 NoneBot 原型。

下一次继续工作，请先读 [设计与实施说明](docs/DESIGN.md)，其中包含用户原话、交互语义、部署关系和近期验收目标。

核心实现已包括 Go MCP、Go Bridge 和 Python/NoneBot QQ 服务端。首版范围为 Codex 与 QQ 的人工交互，以及附带的通知能力；原型保存在相邻的 `nonebot-prototype/`。

## 运行

在仓库根目录构建两个独立程序：

```sh
go build -o bin/request-me-mcp ./cmd/request-me-mcp
go build -o bin/request-me-bridge ./cmd/request-me-bridge
```

服务端安装 `server/requirements.txt`，按 `server/.env.example` 配置环境变量，从仓库根目录执行 `python -m server`。QQ AppID 与 AppSecret 用于 WebSocket 登录；owner openid 是消息接收目标，每个 Bridge 使用独立 token。

MCP 与 Bridge 共享 `config/bridge.example.json` 格式的配置。设置其中 `token_env` 指定的环境变量，将 MCP 程序及 `-config /absolute/path/bridge.local.json` 注册到 Codex；在同一执行主机常驻运行 Bridge，使用对应 Codex 的 app-server 地址。

[协议说明](docs/PROTOCOL.md)记录发送、回程、关闭和回执。当前状态保存在内存中，重启恢复尚未实现。开发验收优先使用真实 QQ 与持久 Codex 任务，离线测试作为补充。
