from nonebot import logger, on_message, on_notice
from nonebot.adapters.qq import Bot
from nonebot.adapters.qq.event import C2CMessageCreateEvent, InteractionCreateEvent
from nonebot.rule import Rule

from .core import RequestError

service = None
owner = ""
app_id = ""


def configure(request_service, owner_openid, bot_id):
    global service, owner, app_id
    service, owner, app_id = request_service, owner_openid, bot_id


async def is_click(event):
    return (isinstance(event, InteractionCreateEvent) and event.type == 11
            and (event.data.resolved.button_data or "").startswith("request:"))


click = on_notice(rule=Rule(is_click), priority=5, block=True)


@click.handle()
async def handle_click(bot: Bot, event: InteractionCreateEvent):
    if (bot.self_id != app_id or event.get_user_id() != owner
            or event.chat_type != 2 or service is None):
        await bot.put_interaction(interaction_id=event.id, code=4)
        return
    try:
        await service.handle_callback_global(event.data.resolved.button_data)
        code = 0
    except RequestError as error:
        code = 3 if error.status == 409 else 1
    except Exception as error:
        logger.error("request-me callback failed: {}", type(error).__name__)
        code = 1
    await bot.put_interaction(interaction_id=event.id, code=code)


async def is_manual(event):
    return (isinstance(event, C2CMessageCreateEvent)
            and event.get_plaintext().strip().startswith("/respond"))


manual = on_message(rule=Rule(is_manual), priority=5, block=True)


@manual.handle()
async def handle_manual(bot: Bot, event: C2CMessageCreateEvent):
    if bot.self_id != app_id or event.get_user_id() != owner or service is None:
        return
    try:
        await service.handle_manual_global(event.get_plaintext())
    except RequestError as error:
        await bot.send(event, error.message)
    except Exception as error:
        logger.error("request-me manual reply failed: {}", type(error).__name__)
        await bot.send(event, "回答处理失败，请稍后重试。")
