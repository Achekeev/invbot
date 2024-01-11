import logging
from aiogram import Router, Bot

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram_dialog import DialogManager
from ...db import AsyncSession
from ...db.repo import UserRepo
from ...async_task import tasks_queue, Task
from ...messages import messages
from ...filters import AdminFilter

logger = logging.getLogger(__name__)
router = Router(name=__name__)
router.message.filter(AdminFilter())

class BcastState(StatesGroup):
    message = State()


#@router.message(Command('bcast'))
async def bcast_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager):
    logger.info('command [admin]: help')

    await dialog_manager.reset_stack()
    await state.set_state(BcastState.message)
    await msg.answer(messages.input_message())

@router.message(BcastState.message)
async def bcast_message(msg: Message, bot: Bot, state: FSMContext, session: AsyncSession):
    await state.clear()
    if not msg.text:
        return
    async with session.begin():
        user_repo = UserRepo(session)
        users = await user_repo.get_bcast()
        async for row in users:
            user = row[0]
            task = Task(bot=bot, chat_id=user.chat_id, text=msg.text, reply_markup=None)
            tasks_queue.put_nowait(task)
