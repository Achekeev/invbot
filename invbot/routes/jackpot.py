import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram_dialog import DialogManager
from ..messages import messages

logger = logging.getLogger(__name__)

router = Router(name=__name__)
router.message.filter(F.chat.type=='private')

async def jackpot_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager):
    logger.info('command: help')
    await dialog_manager.reset_stack()
    await msg.answer(messages.jackpot())