import asyncio

import pytest

from .core import RequestError, RequestService
from .models import Option, RequestIn


class Sender:
    def __init__(self):
        self.requests = []
        self.notifications = []

    async def send_request(self, message):
        self.requests.append(message)
        await asyncio.sleep(0)
        return f"qq-{len(self.requests)}"

    async def send_notification(self, message):
        self.notifications.append(message)
        return f"qq-n-{len(self.notifications)}"


@pytest.mark.asyncio
async def test_concurrent_request_is_idempotent_and_buttons_are_explicit():
    sender = Sender()
    service = RequestService(sender)
    item = RequestIn(id="r1", thread_id="t1", markdown="# stop?", options=[Option(id="yes", label="Yes")])
    records = await asyncio.gather(*(service.create_request("b", item) for _ in range(5)))
    assert len(sender.requests) == 1
    assert {r.message_id for r in records} == {"qq-1"}
    assert [b.kind for b in sender.requests[0].buttons] == ["option", "manual", "close"]
    assert sender.requests[0].buttons[1].value == f"/respond {records[0].code} "


@pytest.mark.asyncio
async def test_first_answer_wins_and_bridge_scope_isolated():
    sender = Sender()
    service = RequestService(sender)
    item = RequestIn(id="r1", thread_id="t1", markdown="question")
    await service.create_request("b1", item)
    await service.create_request("b2", item.model_copy(update={"id": "r2"}))
    first = await service.handle_manual("b1", "/respond r1 choice")
    assert first.text == "choice"
    with pytest.raises(RequestError):
        await service.handle_manual("b1", "/respond r1 second")
    with pytest.raises(RequestError):
        await service.handle_manual("b2", "/respond r1 wrong")

    found = await service.poll("b1", wait=0)
    assert [a.id for a in found] == [first.id]
    assert await service.poll("b1", wait=0) == []
    await service.receipt("b1", first.id, "accepted", "queued")


@pytest.mark.asyncio
async def test_close_checks_thread_and_does_not_create_answer():
    sender = Sender()
    service = RequestService(sender)
    await service.create_request("b", RequestIn(id="r", thread_id="thread", markdown="x"))
    with pytest.raises(RequestError):
        await service.close("b", "r", "other")
    await service.close("b", "r", "thread")
    with pytest.raises(RequestError):
        await service.handle_manual("b", "/respond r no")
