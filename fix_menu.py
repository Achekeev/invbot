#!/usr/bin/env python3

import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommandScopeChat, BotCommandScopeAllPrivateChats
from aiogram.enums import ParseMode
from invbot.db import session_maker
from invbot.db.repo import UserRepo
from invbot import bot_commands
import settings

async def on_start(bot: Bot):
    result = await bot.set_my_commands(bot_commands, BotCommandScopeAllPrivateChats())
    logging.info('private chat commands set: %s', result)
    async with session_maker() as session:
        async with session.begin():
            user_repo = UserRepo(session)
            users = await user_repo.get_all_stream()
            async for row in users:
                user = row[0]
                result = await bot.delete_my_commands(BotCommandScopeChat(chat_id=user.chat_id)) 
                logging.info('chat commande deleted for: %d :: %s', user.chat_id, result)       

async def main():
    logging.basicConfig(format='%(asctime)s [%(levelname)s]:%(name)s %(message)s', level=getattr(logging, settings.LOGLEVEL.upper()))
    logging.info('fix menu')
    assert settings.BOT_TOKEN

    bot = Bot(settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.startup.register(on_start)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

asyncio.run(main())
