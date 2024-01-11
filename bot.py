#!/usr/bin/env python3

import settings
import logging
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import BotCommandScopeAllPrivateChats
from aiogram.filters import CommandStart, Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.enums import ParseMode
from aiogram.utils.i18n import I18n
from aiogram.utils.i18n.middleware import ConstI18nMiddleware
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram_dialog import setup_dialogs
import aiohttp
from aiohttp import web
from aiohttp_remotes import setup, XForwardedStrict
import redis.asyncio as redis
from invbot.routes import (
    start_cmd, settings_cmd, help_cmd, payin_cmd, payout_cmd, jackpot_cmd,
    unknown_msg_router, ask_cmd, registration_cmd
)
from invbot.routes import start_router, settings_router, help_router, payin_router, payout_router
from invbot.routes.admin import (
    admin_chat_router, 
    admin_help_router,
    admin_user_dialog_router,
    admin_bcast_router,
    admin_transaction_router,
    admin_transaction_dialog_router,
    admin_csv_export_router,
    admin_set_account_router,

    # bcast_cmd,
    # txl_cmd,
    # tx_cmd,
    # user_export_cmd,
    # tx_export_cmd,
    # id_cmd,
    # regs_cmd,
    # sync_cmd
    admin_cmd_router
)
from invbot.middleware import DBSessionMeddleware, PreloadDataMiddleware
from invbot.db import session_maker
from invbot import async_task
from invbot import bithide
from invbot.filters import UserFilter
from invbot import bot_commands

# # Error handlers
# @dp.error(ExceptionTypeFilter(BotError), F.update.message.as_('message'))
# async def bot_error_message_handler(event: ErrorEvent, message: Message):
#     logging.error(event.exception)
#     if isinstance(event.exception, BotError):
#         await event.exception.answer_message(message)

# @dp.error(ExceptionTypeFilter(BotError), F.update.callback_query.as_('callback'))
# async def bot_error_callback_handler(event: ErrorEvent, callback: CallbackQuery):
#     logging.error(event.exception)
#     if isinstance(event.exception, BotError):
#         await event.exception.answer_callback(callback)

async def on_startup(bot: Bot) -> None:
    await bot.set_webhook(f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}", secret_token=settings.WEBHOOK_SECRET)
    logging.info('webhook set: %s', f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}")
    result = await bot.set_my_commands(bot_commands, BotCommandScopeAllPrivateChats())
    logging.info('bot commands set: %s', 'OK' if result else 'FAILED')

async def main():
    # setup logger
    logging.basicConfig(format='%(asctime)s [%(levelname)s]:%(name)s %(message)s', level=getattr(logging, settings.LOGLEVEL.upper()))
    logging.info('invbot started')

    logging.info('bithide: url=%s, callback_url=%s', settings.BITHIDE_URL, settings.BITHIDE_CALLBACK_URL)
    #cache = await create_cache(settings.DEV)

    if settings.REDIS_URL:
        logging.info('use redis storage at: %s, lifetime: %ds', settings.REDIS_URL, settings.REDIS_LIFETIME)
        storage = RedisStorage(
            redis.from_url(settings.REDIS_URL),
            state_ttl=settings.REDIS_LIFETIME,
            data_ttl=settings.REDIS_LIFETIME,
            key_builder=DefaultKeyBuilder(with_bot_id=True, with_destiny=True)
        )
    else:
        logging.info('use internal memory storage')
        storage = MemoryStorage()
    
    dp = Dispatcher(storage=storage)
    setup_dialogs(dp)

    # top level commands
    dp.message.register(start_cmd, CommandStart(), F.chat.type=='private')
    dp.message.register(settings_cmd, Command('settings'), F.chat.type=='private', UserFilter())
    dp.message.register(payin_cmd, Command('payin'), F.chat.type=='private', UserFilter())
    dp.message.register(payout_cmd, Command('payout'), F.chat.type=='private', UserFilter())
    dp.message.register(jackpot_cmd, Command('jackpot'), F.chat.type=='private', UserFilter())
    dp.message.register(help_cmd, Command('help'))
    dp.message.register(ask_cmd, Command('ask'))
    dp.message.register(registration_cmd, Command('registration'))

    # setup dispatcher
    dp.include_routers(
        admin_chat_router, admin_cmd_router,
        admin_transaction_router, admin_set_account_router,
        start_router, settings_router, help_router, payin_router, payout_router, 
        admin_help_router, admin_user_dialog_router,
        admin_bcast_router, admin_transaction_dialog_router,
        admin_csv_export_router,
        unknown_msg_router,
    )

    # setup messages translation
    i18n = I18n(path="locales", default_locale="ru", domain="messages")
    dp.update.middleware(ConstI18nMiddleware('ru', i18n))

    # DB session
    dp.update.middleware(DBSessionMeddleware(session_maker))

    # Data middleware (curernt user, settings, ...)
    dp.update.middleware(PreloadDataMiddleware())

    # aiohttp client session
    dp['client_session'] = aiohttp.ClientSession()

    if settings.WEBHOOK_URL and settings.WEBHOOK_PATH:
        dp.startup.register(on_startup)

    async_task.start()

    # create bot
    assert settings.BOT_TOKEN
    bot = Bot(settings.BOT_TOKEN, parse_mode=ParseMode.HTML)

    app = web.Application()
    app['bot'] = bot
    app['session_maker'] = session_maker
    app['i18n'] = i18n

    app.add_routes([web.post(settings.BITHIDE_CALLBACK_MOUNT, bithide.callback)])

    # set reverse proxy list
    if settings.REVERSE_PROXIES:
        logging.info('set reverse proxy check: trusts=%s, white_paths=%s', settings.REVERSE_PROXIES, settings.WHITE_PATHS)
        await setup(app, XForwardedStrict(settings.REVERSE_PROXIES, white_paths=settings.WHITE_PATHS))

    if settings.WEBHOOK_URL and settings.WEBHOOK_PATH:
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=settings.WEBHOOK_SECRET,
        )
        webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=settings.HTTP_PORT)

    if settings.WEBHOOK_URL and settings.WEBHOOK_PATH:
        logging.info('start in webhook mode')
        await site.start()
        while True:
            await asyncio.sleep(3600) 
    else:
        logging.info('start in long poll mode')
        await site.start()
        await dp.start_polling(bot)


asyncio.run(main())
