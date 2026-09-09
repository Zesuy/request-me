"""Configured HTTP applications. Business commands and cards belong to the caller."""
import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field, HttpUrl, model_validator

from .core import QQButton, QQMessage, RequestError


class Action(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,32}$")
    label: str = Field(min_length=1, max_length=80)
    value: dict[str, Any] = Field(default_factory=dict)


class Card(BaseModel):
    markdown: str = Field(min_length=1, max_length=30000)
    actions: list[Action] = Field(default_factory=list, max_length=8)
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_card(self):
        if not self.markdown.strip() or len({a.id for a in self.actions}) != len(self.actions):
            raise ValueError("card requires text and unique action ids")
        return self


class Application(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    command: str = Field(pattern=r"^/[A-Za-z][A-Za-z0-9_-]*$")
    endpoint: HttpUrl
    token_env: str = Field(min_length=1)
    timeout: float = Field(default=100, ge=1, le=300)


def load_applications(path: str | None) -> list[Application]:
    if not path:
        return []
    apps = [Application.model_validate(a) for a in json.loads(Path(path).read_text(encoding="utf-8"))]
    if len({a.id for a in apps}) != len(apps) or len({a.command for a in apps}) != len(apps):
        raise ValueError("application ids and commands must be unique")
    for app in apps:
        if app.command == "/respond" or not os.getenv(app.token_env):
            raise ValueError(f"reserved command or missing token for application {app.id}")
        if app.endpoint.username or app.endpoint.password:
            raise ValueError("put application credentials in token_env")
    return apps


@dataclass
class StoredCard:
    application: Application
    card: Card
    created: float
    consumed: bool = False


class ApplicationService:
    def __init__(self, apps, sender, *, client=None):
        self.apps = {a.command: a for a in apps}
        self.sender = sender
        self.client = client or httpx.AsyncClient(follow_redirects=False)
        self.cards: dict[str, StoredCard] = {}
        self.events: dict[str, float] = {}

    async def aclose(self):
        await self.client.aclose()

    def match(self, text):
        parts = text.strip().split(maxsplit=1)
        return self.apps.get(parts[0]) if parts else None

    def _prune(self):
        now = time.monotonic()
        self.cards = {k: v for k, v in self.cards.items() if now - v.created < 86400}
        self.events = {k: v for k, v in self.events.items() if now - v < 86400}

    def claim_command(self, event_id):
        self._prune()
        if event_id in self.events:
            return False
        self.events[event_id] = time.monotonic()
        return True

    def claim_action(self, data):
        self._prune()
        parts = data.split(":")
        if len(parts) != 3 or parts[0] != "app":
            raise RequestError(400, "无效操作")
        record = self.cards.get(parts[1])
        if record is None:
            raise RequestError(404, "卡片已过期，请重新发送命令。")
        action = next((a for a in record.card.actions if a.id == parts[2]), None)
        if action is None:
            raise RequestError(400, "无效操作")
        if record.consumed:
            raise RequestError(409, "已提交，请使用最新卡片。")
        record.consumed = True
        return record, action

    async def command(self, app, text, event_id, user_id):
        parts = text.strip().split(maxsplit=1)
        await self._call(app, {"version": 1, "id": event_id, "kind": "command",
                              "user_id": user_id, "text": parts[1] if len(parts) > 1 else ""})

    async def action(self, record, action, event_id, user_id):
        await self._call(record.application, {"version": 1, "id": event_id, "kind": "action",
                         "user_id": user_id, "action": action.model_dump(), "context": record.card.context})

    async def _call(self, app, payload):
        try:
            response = await self.client.post(str(app.endpoint), json=payload,
                headers={"Authorization": "Bearer " + os.environ[app.token_env]}, timeout=app.timeout)
            response.raise_for_status()
            card = Card.model_validate(response.json())
        except (httpx.HTTPError, ValueError, KeyError):
            card = Card(markdown="应用响应未能确认，请查询当前状态后再决定是否重试。")
        code = uuid4().hex[:12]
        self._prune()
        self.cards[code] = StoredCard(app, card, time.monotonic())
        message = QQMessage(code, card.markdown, None,
                            tuple(QQButton(a.id, a.label, "action") for a in card.actions), "card")
        try:
            await asyncio.wait_for(self.sender.send_notification(message), 20)
        except BaseException:
            self.cards[code].consumed = True
            raise
