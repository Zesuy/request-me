import asyncio
from types import SimpleNamespace

import httpx
import pytest

from .app import create_app
from .core import RequestError, RequestService
from .models import NotificationIn, Option, RequestIn, Source
from .qq import render, source_line
from .test_core import Sender


@pytest.mark.asyncio
async def test_same_client_id_across_bridges_routes_by_unique_code():
    service = RequestService(Sender())
    item = RequestIn(id="same-id", thread_id="one", markdown="context", options=[Option(id="a", label="继续", value="重新检查")])
    a = await service.create_request("one", item)
    b = await service.create_request("two", item.model_copy(update={"thread_id": "two"}))
    assert a.code != b.code
    with pytest.raises(RequestError):
        await service.handle_manual_global("/respond same-id ambiguous")
    answer_b = await service.handle_manual_global(f"/respond {b.code} 第二个会话")
    answer_a = await service.handle_callback_global(f"request:{a.code}:option:a")
    assert (answer_a.thread_id, answer_a.text) == ("one", "重新检查")
    assert (answer_b.thread_id, answer_b.text) == ("two", "第二个会话")
    assert [a.id for a in await service.poll("one", 0)] == [answer_a.id]
    assert [a.id for a in await service.poll("two", 0)] == [answer_b.id]


@pytest.mark.asyncio
async def test_notification_is_not_a_question_and_payload_conflicts():
    sender = Sender()
    service = RequestService(sender)
    item = NotificationIn(id="n", thread_id="t", markdown="完成")
    await service.create_notification("b", item)
    await service.create_notification("b", item)
    assert len(sender.notifications) == 1 and sender.notifications[0].buttons == ()
    with pytest.raises(RequestError):
        await service.answer("n", "hello", bridge_id="b")
    with pytest.raises(RequestError):
        await service.create_notification("b", item.model_copy(update={"markdown": "different"}))
    with pytest.raises(RequestError):
        await service.create_request("b", RequestIn(id="n", thread_id="t", markdown="完成"))


@pytest.mark.asyncio
async def test_claim_wait_does_not_return_old_claimed_answer():
    service = RequestService(Sender())
    for i in range(2):
        await service.create_request("b", RequestIn(id=f"q{i}", thread_id="t", markdown="x"))
    first = await service.answer("q0", "first", bridge_id="b")
    assert (await service.poll("b", 0))[0].id == first.id
    waiter = asyncio.create_task(service.poll("b", 1))
    await asyncio.sleep(0)
    second = await service.answer("q1", "second", bridge_id="b")
    assert [a.id for a in await waiter] == [second.id]
    assert await service.poll("b", 0) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["accepted", "failed", "unknown"])
async def test_receipt_is_once_and_scoped(status):
    class Receipts(Sender):
        def __init__(self):
            super().__init__()
            self.receipts = []

        async def send_receipt(self, message):
            self.receipts.append(message)

    sender = Receipts()
    service = RequestService(sender)
    await service.create_request("b", RequestIn(id="q", thread_id="t", markdown="x", source=Source(title="任务")))
    answer = await service.answer("q", "yes", bridge_id="b")
    with pytest.raises(RequestError):
        await service.receipt("b", answer.id, status, "")
    await service.poll("b", 0)
    with pytest.raises(RequestError):
        await service.receipt("other", answer.id, status, "")
    for _ in range(2):
        await service.receipt("b", answer.id, status, "")
    assert answer.receipt == status
    assert len(sender.receipts) == (0 if status == "accepted" else 1)
    if status != "accepted":
        assert sender.receipts[0].source.title == "任务"
    with pytest.raises(RequestError):
        await service.receipt("b", answer.id, status, "different")


@pytest.mark.asyncio
async def test_failed_send_never_returns_success_or_retries_implicitly():
    class Broken(Sender):
        async def send_request(self, message):
            self.requests.append(message)
            raise RuntimeError("connection lost after sending")

    sender = Broken()
    service = RequestService(sender)
    item = RequestIn(id="q", thread_id="t", markdown="x")
    with pytest.raises(RuntimeError):
        await service.create_request("b", item)
    with pytest.raises(RequestError):
        await service.create_request("b", item)
    assert len(sender.requests) == 1


@pytest.mark.asyncio
async def test_http_auth_scoping_idempotency_and_validation():
    app = create_app(sender=Sender(), bridges={"one": "token-one", "two": "token-two"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        data = {"id": "q", "thread_id": "t", "markdown": "question"}
        assert (await http.post("/v1/requests", json=data)).status_code == 401
        http.headers["Authorization"] = "Bearer token-one"
        assert (await http.post("/v1/requests", json=data)).json()["status"] == "sent"
        await app.state.request_service.answer("q", "reply", bridge_id="one")
        assert (await http.post("/v1/requests", json=data)).json()["status"] == "sent"
        http.headers["Authorization"] = "Bearer token-two"
        assert (await http.post("/v1/requests/q/close", json={"thread_id": "t"})).status_code == 404
        assert (await http.get("/v1/answers?wait=0")).json() == {"answers": []}
        assert (await http.post("/v1/requests", json={**data, "options": [{"id": "a", "label": "A"}] * 2})).status_code == 422


@pytest.mark.asyncio
async def test_qq_native_render_preserves_markdown_and_uses_option_id():
    sender = Sender()
    service = RequestService(sender)
    markdown = "正文\n\n| a | b |\n|---|---|\n|1|2|\n\n```text\nraw log\n```"
    rec = await service.create_request("b", RequestIn(id="q", thread_id="t", markdown=markdown,
        source=Source(title="检查日志", cwd="/home/me/tmp", host="WSL"),
        options=[Option(id=f"a{i}", label=f"选项{i}", value=f"实际回答{i}") for i in range(8)]))
    rich = render(sender.requests[0])
    assert rich[0].data["markdown"].content.startswith("⏸️ **等待你的回应**\n\n" + markdown)
    assert "↳ *检查日志* · `tmp` · `WSL`" in rich[0].data["markdown"].content
    rows = rich[1].data["keyboard"].content.rows
    assert len(rows) == 5 and all(len(row.buttons) <= 2 for row in rows)
    assert rows[0].buttons[0].action.type == 1
    assert rows[0].buttons[0].render_data.visited_label == "已提交：选项0"
    assert rows[-1].buttons[0].render_data.visited_label == "人工输入"
    assert rows[-1].buttons[1].render_data.visited_label == "已关闭"
    assert rows[0].buttons[0].action.data == f"request:{rec.code}:option:a0"
    manual = rows[-1].buttons[0].action
    assert manual.type == 2 and manual.enter is False and manual.reply is True
    assert manual.data == f"/respond {rec.code} "
    assert source_line(Source(cwd="D:\\work\\tmp", host="Windows")) == "↳ `tmp` · `Windows`"


def test_notification_and_receipt_presentation():
    from .core import QQMessage
    source = Source(title="任务", cwd="/work/tmp", host="WSL")
    for kind, prefix in [("notification", "🔔 "), ("receipt", "")]:
        message = QQMessage("code", "正文 **保留**", source, (), kind)
        assert render(message)[0].data["markdown"].content == prefix + "正文 **保留**\n\n↳ *任务* · `tmp` · `WSL`"
    assert source_line(Source()) == ""
    assert source_line(Source(title="a*b", host="host`name")) == "↳ *a\\*b* · `` host`name ``"


@pytest.mark.asyncio
async def test_invalid_option_and_close_callback():
    service = RequestService(Sender())
    rec = await service.create_request("b", RequestIn(id="q", thread_id="t", markdown="x"))
    with pytest.raises(RequestError):
        await service.handle_callback_global(f"request:{rec.code}:option:forged")
    await service.handle_callback_global(f"request:{rec.code}:close:_close")
    assert rec.status == "closed" and not service.answers


@pytest.mark.asyncio
async def test_runtime_builds_shared_service_without_connecting():
    from .__main__ import build_runtime
    from .config import Settings
    driver, service = build_runtime(Settings("test-app", "test-secret", "owner", {"b": "token"}))
    from . import plugin
    assert plugin.service is service
    assert driver.config.qq_bots[0]["intent"]["interaction"] is True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=driver.server_app), base_url="http://test") as http:
        response = await http.get("/v1/answers?wait=0", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200 and response.json() == {"answers": []}
