import logging
from typing import Any
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply
from aiogram.utils.i18n import gettext as _
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError
from aiogram_dialog import DialogManager
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from ..db import AsyncSession
from ..db.models import Setting, User, Ext
from ..db.repo import SettingsRepo
from ..callbacks import HelpData
from ..filters import UserFilter
from ..messages import messages


logger = logging.getLogger(__name__)

router = Router(name=__name__)
unknown_msg_router = Router(name=__name__+'_unknown_msg')
unknown_msg_router.message.filter(F.chat.type=='private')


class HelpState(StatesGroup):
    question = State()

@unknown_msg_router.message()
async def unknown_msg_help(msg: Message):
    logger.info('unknown message help')
    await msg.answer(messages.unknown_msg_help())

#@router.message(Command('help'))
async def help_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager, settings: dict[str, Any], is_admin: bool):
    logger.info('command: help')
    await dialog_manager.reset_stack()
    keybord = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=messages.ask_question(), callback_data='uquest')]
    ])
    admin_group_id = settings.get(Setting.Name.ADMIN_GROUP)
    if admin_group_id and admin_group_id == msg.chat.id:
        await msg.answer(messages.admin_help())
    elif is_admin:
        await msg.answer(messages.help() + '\n\n' + messages.admin_help(), reply_markup=keybord) 
    else:
        await msg.answer(messages.help(), reply_markup=keybord)

async def registration_cmd(msg: Message, dialog_manager: DialogManager):
    logger.info('command: registration')
    await dialog_manager.reset_stack()
    keybord = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=messages.ask_question(), callback_data='uquest')]
    ])
    await msg.answer(messages.start_help(), reply_markup=keybord)

@router.message(Command("cancel"))
@router.message(F.text.casefold() == "cancel")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info("Cancelling state %r", current_state)
    await state.clear()
    await message.answer(
        _('Отмена'),
    )

async def ask_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager):
    logger.info('command: ask')
    await dialog_manager.reset_stack()
    await state.set_state(HelpState.question)
    await msg.answer(
        _('Отправте вопрос, для отмены используйте команду /cancel'),
        reply_markup=ForceReply(input_field_placeholder=_('Вопрос'))
    )

@router.callback_query(F.data == 'uquest')
async def help_callback(cbq: CallbackQuery, state: FSMContext, dialog_manager: DialogManager):
    await state.set_state(HelpState.question)
    await cbq.answer()
    if not cbq.message:
        await cbq.answer(messages.bad_callback())
        return   

    await cbq.message.answer(
        _('Отправте вопрос, для отмены используйте команду /cancel'),
        reply_markup=ForceReply(input_field_placeholder=_('Вопрос'))
    )

@router.message(F.text, HelpState.question, UserFilter())
async def help_question(msg: Message, bot: Bot, user: User, state: FSMContext, session: AsyncSession):
    if not msg.text:
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text='Ответить', 
            callback_data=HelpData(chat_id=msg.chat.id, message_id=msg.message_id).pack()
        )]
    ])
    async with session.begin():
        setting_repo = SettingsRepo(session)
        admin_group_id = await setting_repo.get_value(Setting.Name.ADMIN_GROUP)
    if admin_group_id:
        try:
            await bot.send_message(
                admin_group_id,
                _(
                    'Вопрос от:\n'
                    'Ник: {user.username}, тел.: {user.phone_number}\n'
                ).format(user=user) + msg.text,
                reply_markup=keyboard
            )
        except TelegramAPIError as ex:
            logger.error("can't send notification to admins group: %s", ex)
            await msg.answer("В данное время сервис недоступен.")
        else:
            await msg.answer(
                _('Ваш вопрос передан администратору, в ближайшее время Вам придет ответ.')
            )
        await state.clear()