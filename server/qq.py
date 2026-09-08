"""QQ-specific conversion lives exclusively at the sending boundary."""
import re
from pathlib import PurePosixPath, PureWindowsPath

from .core import QQMessage


def source_line(source):
    if source is None:
        return ""
    def clean(value):
        return str(value).replace("\n", " ").replace("\r", " ").strip()

    def code(value):
        value = clean(value)
        fence = "`" * (max((len(m.group()) for m in re.finditer(r"`+", value)), default=0) + 1)
        return f"{fence} {value} {fence}" if "`" in value else f"{fence}{value}{fence}"

    parts = []
    if source.title and clean(source.title):
        title = re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", clean(source.title))
        parts.append(f"*{title}*")
    if source.cwd:
        path = PureWindowsPath(source.cwd) if "\\" in source.cwd or re.match(r"^[A-Za-z]:", source.cwd) else PurePosixPath(source.cwd)
        parts.append(code(path.name or str(path)))
    if source.host and clean(source.host):
        parts.append(code(source.host))
    return "↳ " + " · ".join(parts) if parts else ""


def render(message: QQMessage):
    from nonebot.adapters.qq import Message, MessageSegment
    from nonebot.adapters.qq.models import (
        Action, Button, InlineKeyboard, InlineKeyboardRow, MessageKeyboard, Permission, RenderData,
    )
    source = source_line(message.source)
    prefix = {"request": "⏸️ **等待你的回应**\n\n", "notification": "🔔 "}.get(message.kind, "")
    markdown = prefix + message.markdown + (f"\n\n{source}" if source else "")
    rich = Message([MessageSegment.markdown(markdown)])
    buttons = []
    for index, button in enumerate(message.buttons):
        if button.kind in {"option", "close"}:
            data = f"request:{message.request_id}:{button.kind}:{button.id}"
            action = Action(type=1, permission=Permission(type=2), data=data,
                            unsupport_tips="当前 QQ 客户端不支持回调按钮")
        else:
            action = Action(type=2, permission=Permission(type=2), data=button.value,
                            reply=True, enter=False, unsupport_tips="请手动输入回复")
        visited = {"option": f"已提交：{button.label}", "close": "已关闭", "manual": "人工输入"}[button.kind]
        buttons.append(Button(id=str(index), render_data=RenderData(
            label=button.label, visited_label=visited, style=0), action=action))
    if buttons:
        rows = [InlineKeyboardRow(buttons=buttons[i:i + 2]) for i in range(0, len(buttons), 2)]
        rich += MessageSegment.keyboard(MessageKeyboard(content=InlineKeyboard(rows=rows)))
    return rich


class NoneBotQQSender:
    def __init__(self, bot, *, owner_openid: str):
        self.bot, self.owner_openid = bot, owner_openid

    async def _send(self, message):
        result = await self.bot.send_to_c2c(openid=self.owner_openid, message=render(message))
        message_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        if not message_id:
            raise RuntimeError("QQ did not return a message id")
        return str(message_id)

    async def send_request(self, message):
        return await self._send(message)

    async def send_notification(self, message):
        return await self._send(message)

    async def send_receipt(self, message):
        return await self._send(message)
