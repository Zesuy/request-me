from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from .models import NotificationIn, RequestIn, Source

log = logging.getLogger(__name__)


class QQSender(Protocol):
    async def send_request(self, message: "QQMessage") -> str: ...
    async def send_notification(self, message: "QQMessage") -> str: ...


@dataclass(frozen=True)
class QQButton:
    id: str
    label: str
    kind: str
    value: str | None = None


@dataclass(frozen=True)
class QQMessage:
    request_id: str  # Opaque short code on the QQ side.
    markdown: str
    source: Source | None
    buttons: tuple[QQButton, ...]
    kind: str = "receipt"


@dataclass
class RequestRecord:
    item: RequestIn | NotificationIn
    bridge_id: str
    code: str
    kind: str
    message_id: str = ""
    status: str = "sending"


@dataclass
class AnswerRecord:
    id: str
    request_id: str
    bridge_id: str
    thread_id: str
    text: str
    claimed: bool = False
    receipt: str | None = None
    detail: str = ""


class RequestError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


class RequestService:
    """One server process, in-memory routing and delivery journal."""

    def __init__(self, sender: QQSender):
        self.sender = sender
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
        self.requests: dict[tuple[str, str], RequestRecord] = {}
        self.answers: dict[str, AnswerRecord] = {}

    @staticmethod
    def _message(rec: RequestRecord) -> QQMessage:
        item = rec.item
        buttons = []
        if rec.kind == "request":
            buttons = [QQButton(o.id, o.label, "option") for o in item.options]
            buttons += [QQButton("_manual", "人工输入", "manual", f"/respond {rec.code} "),
                        QQButton("_close", "关闭问题", "close")]
        return QQMessage(rec.code, item.markdown, item.source, tuple(buttons), rec.kind)

    async def _create(self, bridge_id, item, kind) -> RequestRecord:
        async with self._lock:
            key = (bridge_id, item.id)
            old = self.requests.get(key)
            if old:
                # Source can change between retries; first-sent source is retained.
                if old.kind != kind or old.item.model_dump(exclude={"source"}) != item.model_dump(exclude={"source"}):
                    raise RequestError(409, "request id already used with different content")
                if not old.message_id:
                    raise RequestError(409, "previous send is unconfirmed; inspect before resubmission")
                return old
            rec = RequestRecord(item, bridge_id, uuid4().hex[:12], kind)
            while any(r.code == rec.code for r in self.requests.values()):
                rec.code = uuid4().hex[:12]
            self.requests[key] = rec
            send = self.sender.send_request if kind == "request" else self.sender.send_notification
            try:
                message_id = await asyncio.wait_for(send(self._message(rec)), 20)
                if not message_id:
                    raise RuntimeError("missing QQ message id")
            except BaseException:
                rec.status = "send_unknown"
                raise
            rec.message_id, rec.status = str(message_id), "sent"
            return rec

    async def create_request(self, bridge_id: str, item: RequestIn) -> RequestRecord:
        return await self._create(bridge_id, item, "request")

    async def create_notification(self, bridge_id: str, item: NotificationIn) -> str:
        return (await self._create(bridge_id, item, "notification")).message_id

    def _lookup(self, ref: str, bridge_id: str | None = None) -> RequestRecord:
        found = [r for r in self.requests.values()
                 if r.kind == "request" and (r.code == ref or r.item.id == ref)
                 and (bridge_id is None or r.bridge_id == bridge_id)]
        if len(found) != 1:
            raise RequestError(404, "未找到明确对应的问题，请使用该消息的人工输入按钮。")
        return found[0]

    async def close(self, bridge_id: str, request_id: str, thread_id: str) -> None:
        async with self._lock:
            rec = self.requests.get((bridge_id, request_id))
            if rec is None or rec.kind != "request" or rec.item.thread_id != thread_id:
                raise RequestError(404, "request not found")
            self._close(rec)

    @staticmethod
    def _close(rec):
        if rec.status == "closed":
            return
        if rec.status != "sent":
            raise RequestError(409, "这个问题已回复或关闭。")
        rec.status = "closed"

    def _answer(self, req: RequestRecord, text: str) -> AnswerRecord:
        if not text.strip() or len(text) > 8000:
            raise RequestError(400, "请提供 1–8000 字的回答。")
        if req.status != "sent":
            raise RequestError(409, "这个问题已回复或关闭，请勿重复提交。")
        rec = AnswerRecord(str(uuid4()), req.item.id, req.bridge_id, req.item.thread_id, text)
        req.status = "answered"
        self.answers[rec.id] = rec
        self._condition.notify_all()
        return rec

    async def answer(self, request_id: str, text: str, *, bridge_id: str | None = None) -> AnswerRecord:
        async with self._condition:
            return self._answer(self._lookup(request_id, bridge_id), text)

    async def poll(self, bridge_id: str, wait: float = 25) -> list[AnswerRecord]:
        async with self._condition:
            def available():
                return [a for a in self.answers.values()
                        if a.bridge_id == bridge_id and not a.claimed and a.receipt is None]
            if not available() and wait:
                try:
                    await asyncio.wait_for(self._condition.wait_for(lambda: bool(available())), min(wait, 25))
                except asyncio.TimeoutError:
                    return []
            found = available()
            for a in found:
                a.claimed = True
            return found

    async def receipt(self, bridge_id: str, answer_id: str, status: str, detail: str) -> AnswerRecord:
        async with self._lock:
            answer = self.answers.get(answer_id)
            if answer is None or answer.bridge_id != bridge_id:
                raise RequestError(404, "answer not found")
            if not answer.claimed or status not in {"accepted", "failed", "unknown"}:
                raise RequestError(409, "answer was not claimed or receipt is invalid")
            if answer.receipt is not None:
                if (answer.receipt, answer.detail) != (status, detail):
                    raise RequestError(409, "conflicting receipt")
                return answer
            answer.receipt, answer.detail = status, detail
            req = self.requests[(bridge_id, answer.request_id)]
        send = getattr(self.sender, "send_receipt", None)
        if send and status != "accepted":
            labels = {"failed": "回答已保存，但未能启动 Codex 投递。",
                      "unknown": "回答已保存，尚无法确认 Codex 是否收到；请检查原任务。"}
            try:
                await asyncio.wait_for(send(QQMessage(req.code, labels[status], req.item.source, ())), 20)
            except Exception as error:
                log.warning("receipt display failed: %s", type(error).__name__)
        return answer

    async def handle_user_callback(self, bridge_id: str | None, callback: str) -> AnswerRecord | None:
        parts = callback.split(":", 3)
        if len(parts) != 4 or parts[0] != "request":
            raise RequestError(400, "invalid callback")
        _, ref, kind, value = parts
        async with self._condition:
            rec = self._lookup(ref, bridge_id)
            if kind == "close":
                self._close(rec)
                return None
            option = next((o for o in rec.item.options if o.id == value), None)
            if kind != "option" or option is None:
                raise RequestError(400, "这个选项已失效。")
            return self._answer(rec, option.value or option.label)

    async def handle_callback_global(self, callback: str) -> AnswerRecord | None:
        return await self.handle_user_callback(None, callback)

    async def handle_manual(self, bridge_id: str | None, text: str) -> AnswerRecord:
        match = re.fullmatch(r"/respond\s+(\S+)\s+([\s\S]+)", text.strip())
        if not match:
            raise RequestError(400, "请在预填的问题编号后输入回答。")
        return await self.answer(match.group(1), match.group(2).strip(), bridge_id=bridge_id)

    async def handle_manual_global(self, text: str) -> AnswerRecord:
        return await self.handle_manual(None, text)
