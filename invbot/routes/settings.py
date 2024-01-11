import logging
from enum import IntEnum
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.i18n import gettext as _
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram_dialog import DialogManager
from ..db import AsyncSession
from ..db.models import User
from ..messages import messages
from .common import add_ext_ids

logger = logging.getLogger(__name__)

router = Router(name=__name__)
router.message.filter(F.chat.type=='private')

class BcastStatus(IntEnum):
    ON = 1
    OFF = 0

class SettingsAction(IntEnum):
    TOOGLE_BAST = 1
    ADD_EXTIDS  = 2


class SettingsCbData(CallbackData, prefix='ubs'):
    status: BcastStatus

class SettingsState(StatesGroup):
    ext_id = State()


def create_message(user: User):
    btn_text: str
    cb_data: SettingsCbData
    if user.bcast_status:
        btn_text = _('Выключить прием уведомлений')
        cb_data = SettingsCbData(status=BcastStatus.OFF)
    else:
        btn_text = _('Включить прием уведомлений')
        cb_data = SettingsCbData(status=BcastStatus.ON) 

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, callback_data=cb_data.pack())],
        [InlineKeyboardButton(text=_('Добавить ID'), callback_data='uaextids')]
    ])
    
    text = _(
            'Имя telegram: {user.username}\n'
            'Прием уведомлений: {bcast_status}'
    ).format(user=user, bcast_status=user.bcast_status_text)
    return {
        'text': text,
        'reply_markup': keyboard
    }

#@router.message(Command('settings'), UserFilter(F.status==User.Status.ACTIVE))
async def settings_cmd(msg: Message, state: FSMContext, user: User|None, dialog_manager: DialogManager):
    logger.info('command: settings')

    await dialog_manager.reset_stack()
    await msg.answer(**create_message(user)) # type: ignore

@router.callback_query(SettingsCbData.filter())
async def settings_callback(cbq: CallbackQuery, callback_data: SettingsCbData, user: User|None, session: AsyncSession):
    assert cbq.data
    assert user

    async with session.begin():
        user.bcast_status = callback_data.status == BcastStatus.ON
        session.add(user)
    await cbq.answer(_('Прием уведомлений: {bcast_status}').format(bcast_status=user.bcast_status_text))
    if cbq.message:
        await cbq.message.edit_text(**create_message(user)) # type: ignore
    elif cbq.bot:
        await cbq.bot.send_message(user.chat_id, **create_message(user)) # type: ignore

@router.callback_query(F.data=='uaextids')
async def extids_callback(cbq: CallbackQuery, state: FSMContext, user: User|None):
    assert cbq.data
    assert user
    if not cbq.message:
        return
    await cbq.answer('Укажите ID')
    await cbq.message.answer(messages.input_id_request())
    await state.set_state(SettingsState.ext_id)


@router.message(SettingsState.ext_id)
async def ext_ids_handler(msg: Message, bot: Bot, state: FSMContext, user: User, session: AsyncSession):
    if await add_ext_ids(msg, bot, state, user, session):
        # send notification to admins group
        await msg.answer(
            _(
                'Спасибо, ID добавлены. Вы можете пополнять счета и выводить средства.\n'
                '/payin - пополнение счета\n'
                '/payout - выведение средств'
            )
        )
        await state.clear()
