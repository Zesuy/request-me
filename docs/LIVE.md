# 真实联调现场

2026-09-08：新 Go MCP 已由真实 WSL Codex 调用，QQ 已接受请求；用户点击 A 后，Go Bridge 将回答送回同一个任务，Agent 调用新 MCP 的 notify，QQ 接受回报。随后人工输入“这是一个回复测试会话”也回到同一任务，Agent 原样引用并通过 QQ 回报。按钮与人工输入两条真实闭环均已通过。

- QQ 服务：Windows 本仓库 `python -m server`，监听 `127.0.0.1:8080`，隐藏后台进程。
- WSL 反向隧道：`127.0.0.1:18080 → Windows 127.0.0.1:8080`。
- WSL Bridge：systemd 用户单元 `request-me-bridge.service`。
- Codex MCP 注册名：`request_me`；旧 `localmanage` 注册已移除，旧 Bridge 服务已停止。
- 实际测试任务：`生成随机16进制码`，ID `01a07bde-f801-7992-bb5d-b80b58adac3f`，目录 `/home/zesuy/work/github/tmp`。
- Codex CLI：`/home/zesuy/.local/bin/codex`，版本 0.149.0。

本次临时启动脚本和凭据复用入口在忽略目录 `.local/`，日志在 `.local/logs/`；不复制凭据进源码。运行时仍借用原型 Python 环境，正式安装与服务部署待整理。

用户截图确认：会话标题、项目目录简称与 WSL 主机名均正常显示；两个真实任务的按钮回复也已验证正常。单独的 socket 诊断连接曾失败，不能据此判定实际 MCP 来源补全失败。

新版 Markdown 样式已真实发送并获用户确认。随后已移除成功投递的聊天气泡、将选项按钮改为“已提交”；该最后修改已通过检查，运行中的服务尚未重启加载。
