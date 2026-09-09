import httpx
import pytest

from .applications import Application, ApplicationService, Card, load_applications
from .core import RequestError
from .qq import render


@pytest.mark.asyncio
async def test_two_apps_callbacks_route_to_original_endpoint_and_do_not_replay(monkeypatch):
    monkeypatch.setenv("TEST_APP_TOKEN", "private")
    calls, messages = [], []

    async def handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer private"
        return httpx.Response(200, json={"markdown": "**原始正文**\n\n```txt\nx\n```",
            "actions": [{"id": "go", "label": "执行", "value": {"op": "run"}}], "context": {"task": "a"}})

    class Sender:
        async def send_notification(self, message):
            messages.append(message)
            return "qq-id"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        apps = [Application(id=n, command="/" + n, endpoint=f"https://{n}.test/events", token_env="TEST_APP_TOKEN")
                for n in ("one", "two")]
        service = ApplicationService(apps, Sender(), client=client)
        assert service.match("/one status") == apps[0]
        assert service.match("/one-other") is None
        assert service.claim_command("event")
        assert not service.claim_command("event")
        for app in apps:
            await service.command(app, app.command + " status", app.id, "owner")
        data = f"app:{messages[0].request_id}:go"
        record, action = service.claim_action(data)
        await service.action(record, action, "click", "owner")
        assert [r.url.host for r in calls] == ["one.test", "two.test", "one.test"]
        import json
        assert json.loads(calls[-1].content)["context"] == {"task": "a"}
        with pytest.raises(RequestError):
            service.claim_action(data)
        rich = render(messages[0])
        assert rich[0].data["markdown"].content == messages[0].markdown
        assert rich[1].data["keyboard"].content.rows[0].buttons[0].action.data == data


@pytest.mark.asyncio
async def test_redirect_not_followed_and_unknown_operation_not_retried(monkeypatch):
    monkeypatch.setenv("TEST_APP_TOKEN", "private")
    calls, messages = [], []
    async def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://elsewhere.test"})
    class Sender:
        async def send_notification(self, message):
            messages.append(message)
            return "qq-id"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        app = Application(id="a", command="/a", endpoint="https://app.test", token_env="TEST_APP_TOKEN")
        service = ApplicationService([app], Sender(), client=client)
        await service.command(app, "/a", "event", "owner")
        assert len(calls) == 1
        assert messages[0].buttons == ()
        assert "未能确认" in messages[0].markdown


def test_config_fails_before_accepting_ambiguous_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_APP_TOKEN", "private")
    import json
    app = dict(id="a", command="/a", endpoint="https://app.test", token_env="TEST_APP_TOKEN")
    path = tmp_path / "apps.json"
    path.write_text(json.dumps([app, app]))
    with pytest.raises(ValueError):
        load_applications(str(path))
    with pytest.raises(ValueError):
        Card(markdown="x", actions=[dict(id="a", label="a"), dict(id="a", label="b")])
