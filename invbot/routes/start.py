import logging
from typing import Any
from datetime import datetime, UTC
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ContentType, 
    ReplyKeyboardRemove,
    BotCommandScopeAllPrivateChats,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.i18n import gettext as _
from aiogram_dialog import DialogManager
from invbot.db.models import User, Setting
from invbot import bot_commands
from ..db import AsyncSession
from ..messages import messages
from .common import add_ext_ids
from ..tools import normalize_phone
from ..callbacks import UserRegData

logger = logging.getLogger(__name__)

router = Router(name=__name__)
router.message.filter(F.chat.type=='private')

class StartState(StatesGroup):
    contact = State()
    ext_ids = State()


#@router.message(CommandStart())
async def start_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager):
    logger.debug('/start')
    await dialog_manager.reset_stack()
    await state.set_state(StartState.contact)

    await msg.answer(
        messages.contact_data(msg.from_user),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=messages.Buttons.SEND_CONTACT, request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

@router.message(
    StartState.contact, 
    F.content_type==ContentType.CONTACT, 
    F.from_user, 
)
async def contact(msg: Message, state: FSMContext, session: AsyncSession, bot: Bot, user: User|None, settings: dict[str, Any]):
    assert msg.contact
    assert msg.from_user

    now = datetime.now(UTC)
    is_new_reg = False
    phone_number = normalize_phone(msg.contact.phone_number)
    async with session.begin():
        if user is not None:
            user.phone_number = phone_number
            user.user_id = msg.from_user.id
            user.chat_id = msg.chat.id
            user.last_visited = now
            user.username = msg.from_user.username
            user.first_name = msg.contact.first_name
            user.last_name = msg.contact.last_name
        else:
            user = User(
                phone_number=phone_number,
                user_id=msg.from_user.id,
                chat_id=msg.chat.id,
                last_visited=now,
                username=msg.from_user.username,
                first_name=msg.contact.first_name,
                last_name=msg.contact.last_name
            )
            is_new_reg = True
        session.add(user)
        await session.flush()

    #await bot.set_my_commands(bot_commands, BotCommandScopeAllPrivateChats())    
    #await bot.set_my_commands(bot_commands, BotCommandScopeChat(chat_id=msg.chat.id))
    if is_new_reg:
        keybord = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=messages.ask_question(), callback_data='uquest')]
        ])
        await msg.answer(messages.start_help(), reply_markup=keybord)
        await msg.answer(messages.input_id_request(), reply_markup=ReplyKeyboardRemove())
        await state.set_state(StartState.ext_ids)
    else:
        await msg.answer(messages.already_registered(), reply_markup=ReplyKeyboardRemove())
        await state.clear()
        
@router.message(StartState.ext_ids)
async def ext_ids_handler(msg: Message, bot: Bot, state: FSMContext, user: User, settings: dict[str, Any], session: AsyncSession):
    if await add_ext_ids(msg, bot, state, user, session):
        # send notification to admins group
        admin_group_id = settings.get(Setting.Name.ADMIN_GROUP)
        if admin_group_id:
            await bot.send_message(
                admin_group_id, 
                messages.new_user_registered(user), 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text=messages.Buttons.SET_CARD, callback_data=UserRegData(user_id=user.id).pack())
                    ]
            ]))
        await msg.answer(
            messages.thank_you_register(),
        )
        await state.clear()
