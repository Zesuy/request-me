from __future__ import annotations

import secrets
from fastapi import FastAPI, Header, HTTPException, Query

from .core import QQSender, RequestError, RequestService
from .models import CloseIn, NotificationIn, ReceiptIn, RequestIn


def create_app(*, sender: QQSender, bridges: dict[str, str]) -> FastAPI:
    """Create the HTTP edge. ``bridges`` maps bridge id to bearer token."""
    service = RequestService(sender)
    app = FastAPI(title="request-me QQ server", version="0.1.0")
    app.state.request_service = service

    def auth(authorization: str | None) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token")
        token = authorization[7:]
        for bridge_id, expected in bridges.items():
            if secrets.compare_digest(token, expected):
                return bridge_id
        raise HTTPException(401, "invalid bearer token")

    def fail(error: RequestError) -> None:
        raise HTTPException(error.status, error.message)

    @app.post("/v1/requests")
    async def request(item: RequestIn, authorization: str | None = Header(default=None)):
        bridge_id = auth(authorization)
        try:
            rec = await service.create_request(bridge_id, item)
        except RequestError as error:
            fail(error)
        return {"id": rec.item.id, "status": "sent", "message_id": rec.message_id}

    @app.post("/v1/notifications")
    async def notification(item: NotificationIn, authorization: str | None = Header(default=None)):
        bridge_id = auth(authorization)
        try:
            message_id = await service.create_notification(bridge_id, item)
        except RequestError as error:
            fail(error)
        return {"id": item.id, "status": "sent", "message_id": message_id}

    @app.post("/v1/requests/{request_id}/close")
    async def close(request_id: str, item: CloseIn, authorization: str | None = Header(default=None)):
        bridge_id = auth(authorization)
        try:
            await service.close(bridge_id, request_id, item.thread_id)
        except RequestError as error:
            fail(error)
        return {"id": request_id, "status": "closed"}

    @app.get("/v1/answers")
    async def answers(wait: float = Query(default=25, ge=0, le=25), authorization: str | None = Header(default=None)):
        bridge_id = auth(authorization)
        found = await service.poll(bridge_id, wait)
        return {"answers": [{"id": a.id, "request_id": a.request_id, "thread_id": a.thread_id, "text": a.text} for a in found]}

    @app.post("/v1/answers/{answer_id}/receipt")
    async def receipt(answer_id: str, item: ReceiptIn, authorization: str | None = Header(default=None)):
        bridge_id = auth(authorization)
        try:
            answer = await service.receipt(bridge_id, answer_id, item.status, item.detail)
        except RequestError as error:
            fail(error)
        return {"id": answer.id, "status": answer.receipt}

    return app
