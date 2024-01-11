import logging
import asyncio
from dataclasses import dataclass
from aiogram import Bot
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, ForceReply, ReplyKeyboardRemove
from aiogram.exceptions import TelegramAPIError, TelegramNotFound
import settings

logger = logging.getLogger(__name__)

@dataclass
class Task:
    bot: Bot
    chat_id: int
    text: str
    reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ForceReply | ReplyKeyboardRemove | None

tasks_queue = asyncio.Queue[Task]()


def start():
    return asyncio.create_task(worker())


# def schedule(coro: Coroutine[Any, Any, Any], *args: Iterable[Any]):
#     tasks_queue.put_nowait(coro)


async def worker():
    while True:
        task = await tasks_queue.get()
        try:
            await task.bot.send_message(
                chat_id=task.chat_id,
                text=task.text,
                reply_markup=task.reply_markup
            )
        except TelegramNotFound:
            logger.error('chat_id=%d not found', task.chat_id)
        except TelegramAPIError as ex:
            logger.exception(ex)
        await asyncio.sleep(settings.BCAST_PAUSE)

# async def worker():
#     logging.info('worker started')
#     while True:
#         coro = await tasks_queue.get()
#         try:
#             await coro
#         except Exception as e:
#             logging.error(e)
#         finally:
#             tasks_queue.task_done()
