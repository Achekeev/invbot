import logging
from aiogram import Router, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from ...callbacks import HelpData
from ...filters import AdminFilter

logger = logging.getLogger(__name__)

router = Router(name=__name__)
router.message.filter(AdminFilter())

class HelpState(StatesGroup):
    answer = State()

@router.callback_query(HelpData.filter())
async def help_callback(cbq: CallbackQuery, callback_data: HelpData, state: FSMContext):
    assert callback_data
    await state.set_state(HelpState.answer)
    await state.update_data(chat_id=callback_data.chat_id, message_id=callback_data.message_id)
    if cbq.message:
        await cbq.message.answer(_('Введите ответ, <b>ответив</b> на данное сообщение'))
        await cbq.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))

@router.message(HelpState.answer)
async def help_answer(msg: Message, state: FSMContext, bot: Bot):
    if not msg.text:
        return
    data = await state.get_data()
    assert data
    try:
        await bot.send_message(
            data['chat_id'],
            _('Получен ответ:\n') + msg.text,
            reply_to_message_id=data['message_id']
        )
    except TelegramAPIError as ex:
        logger.error("can't send answer: %s", ex)
        await msg.answer(_('Невозможно отправить ответ'))
    else:
        await msg.answer(_('Ответ отправлен пользователю'))
    await state.clear()
