from .app import create_app
from .config import load_settings
from .qq import NoneBotQQSender
from .applications import ApplicationService, load_applications


def build_runtime(settings):
    import nonebot
    from nonebot.adapters.qq import Adapter as QQAdapter

    nonebot.init(
        driver="~fastapi+~httpx+~websockets",
        host=settings.host, port=settings.port,
        qq_bots=[{"id": settings.app_id, "secret": settings.app_secret, "use_websocket": True,
                  "intent": {"c2c_group_at_messages": True, "interaction": True}}],
    )
    driver = nonebot.get_driver()
    driver.register_adapter(QQAdapter)

    class Sender:
        async def _send(self, message, kind):
            bot = nonebot.get_bots().get(settings.app_id)
            if bot is None:
                raise RuntimeError("QQ bot is not connected")
            sender = NoneBotQQSender(bot, owner_openid=settings.owner_openid)
            return await getattr(sender, kind)(message)

        async def send_request(self, message):
            return await self._send(message, "send_request")

        async def send_notification(self, message):
            return await self._send(message, "send_notification")

        async def send_receipt(self, message):
            return await self._send(message, "send_receipt")

    sender = Sender()
    applications = ApplicationService(load_applications(settings.applications_file), sender)
    driver.on_shutdown(applications.aclose)
    app = create_app(sender=sender, bridges=settings.bridge_tokens)
    loaded = nonebot.load_plugin("server.plugin")
    if loaded is None:
        raise RuntimeError("could not load QQ interaction plugin")
    from . import plugin
    plugin.configure(app.state.request_service, settings.owner_openid, settings.app_id, applications)
    driver.server_app.include_router(app.router)
    return driver, app.state.request_service


def main():
    import nonebot
    build_runtime(load_settings())
    nonebot.run()


if __name__ == "__main__":
    main()
