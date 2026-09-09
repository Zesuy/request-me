# 真实联调现场

2026-09-09：通用 HTTP 应用接入与 Bath 独立接入端已完成源码实现。通过临时本地 HTTP 接入端，通用路由真实调用 `mi9.lan:8765/v1/bath/status`，取得 `COMPLETED` 和 `START` 操作；保存卡片后触发刷新动作，再次查询成功。QQ Markdown 与原生回调结构已本地验证；此次未调用开始、停止或支付。服务端 18 项测试与 Bath 接入端 2 项测试通过。新应用代码尚未部署到 j1900，QQ 命令/按钮实机验收待部署后执行。

2026-09-08：最初的 Go MCP 已由真实 WSL Codex 调用，QQ 已接受请求；用户点击 A 后，Bridge 将回答送回同一个任务，Agent 调用 MCP 的通知工具，QQ 接受回报。随后人工输入“这是一个回复测试会话”也回到同一任务，Agent 原样引用并通过 QQ 回报。按钮与人工输入两条真实闭环均已通过。

同日，MCP 与 Bridge 已等价迁移到同一个 Node.js/TypeScript 包。Node MCP 已在 WSL 使用真实配置完成 stdio 初始化和 `tools/list`，返回 `request_user_response`、`send_user_notification`、`close_user_request`；Node 与 Python 请求中心的双 Bridge 路由集成测试通过。

2026-09-09：WSL MCP 启动入口和 Bridge 服务已切换到 Node。新建的真实 Codex CLI 任务通过 Node MCP 向 QQ 发出选择请求，用户点击“确认 Node 链路”后，Node Bridge 领取回答并成功提交回执。Codex 持久队列中的记录指向原任务 `01a084a3-ee70-7f02-9127-fc43a6d3c1a7`，回答正文与按钮值一致。该 CLI 任务已 detach，因此输入保留在原任务队列中，待任务下次加载时继续。QQ 服务与隧道未重启。

随后关闭了唯一仍待回答的旧按钮数量测试，并重启 Windows QQ 服务加载当前代码。QQ WebSocket 已重新连接，WSL Node Bridge 在短暂断线后恢复长轮询；服务端配置包含互不相同的 `wsl`、`windows` 两个 Bridge 身份。Windows Codex 已写入 `request_me` STDIO MCP 配置并通过独立握手验证工具清单，等待用户自行重启 Codex 后在新任务中生效。按用户要求，Windows Bridge 仅准备私密配置与启动入口，尚未常驻启动。

- QQ 服务：Windows 本仓库 `python -m server`，监听 `127.0.0.1:8080`，隐藏后台进程。
- WSL 反向隧道：`127.0.0.1:18080 → Windows 127.0.0.1:8080`。
- WSL Bridge：systemd 用户单元 `request-me-bridge.service`，运行 Node 入口 `dist/bin/request-me-bridge.js`。
- Codex MCP 注册名：`request_me`，启动入口已指向 `dist/bin/request-me-mcp.js`；旧 `localmanage` 注册已移除，旧 Go Bridge 已停止。
- 实际测试任务：`生成随机16进制码`，ID `01a07bde-f801-7992-bb5d-b80b58adac3f`，目录 `/home/zesuy/work/github/tmp`。
- Node 切换验收任务：ID `01a084a3-ee70-7f02-9127-fc43a6d3c1a7`，同一目录。
- Codex CLI：`/home/zesuy/.local/bin/codex`，版本 0.149.0。

本次临时启动脚本和凭据复用入口在忽略目录 `.local/`，日志在 `.local/logs/`；不复制凭据进源码。运行时仍借用原型 Python 环境，正式安装与服务部署待整理。

已有任务可能保留旧的 MCP 工具清单；切换实现后使用新的 Codex 进程或重新加载工具。此次验收的新 CLI 任务已实际加载 Node MCP。

用户截图确认：会话标题、项目目录简称与 WSL 主机名均正常显示；两个真实任务的按钮回复也已验证正常。单独的 socket 诊断连接曾失败，不能据此判定实际 MCP 来源补全失败。

新版 Markdown 样式已真实发送并获用户确认。随后已移除成功投递的聊天气泡、将选项按钮改为“已提交”；该最后修改已通过检查，运行中的服务尚未重启加载。
