import logging
from typing import Any
from enum import StrEnum
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, ContentType, Message
from aiogram.fsm.state import StatesGroup, State
from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Select, SwitchTo, ScrollingGroup, Cancel
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.text import Const, Format

from ...callbacks import UserRegData
from ...db import AsyncSession
from ...db.models import Account
from ...db.repo import AccountRepo, UserRepo
from ...messages import messages

logger = logging.getLogger(__name__)

router = Router(name=__name__)

class DialogDataKeys(StrEnum):
    ACCOUNTS = 'accounts'
    USER_ID  = 'user_id'
    USER     = 'user'
    BACK_BTN = 'back_btn'

class SelectAccountState(StatesGroup):
    select = State()
    input_new = State()
    finish = State()


async def get_accounts(dialog_manager: DialogManager, session: AsyncSession, **kwargs: Any):
    start_data: dict[str, Any] = dialog_manager.start_data
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    middleware_data: dict[str, Any] = dialog_manager.middleware_data
    assert isinstance(dialog_data, dict)
    assert isinstance(middleware_data, dict)
    assert isinstance(start_data, dict)
    
    user_id: int = start_data[DialogDataKeys.USER_ID]
    async with session.begin():
        user_repo = UserRepo(session)
        user = await user_repo.get_by_id(user_id, related=True)
        account_repo = AccountRepo(session)
        accounts = list(await account_repo.get_all())
    logger.info('got payin accounts: %d', len(accounts))
    return {DialogDataKeys.ACCOUNTS: accounts, DialogDataKeys.USER: user}


async def on_account_click(event: CallbackQuery, select: Select[int], dialog_manager: DialogManager, data: int):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    start_data: dict[str, Any] = dialog_manager.start_data
    middleware_data: dict[str, Any] = dialog_manager.middleware_data
    assert isinstance(dialog_data, dict)
    assert isinstance(start_data, dict)
    assert isinstance(middleware_data, dict)

    if not event.message:
        await event.answer(messages.bad_callback(), show_alert=True)
        return
    session: AsyncSession = middleware_data['session']
    user_id: int = int(start_data[DialogDataKeys.USER_ID])
    async with session.begin():
        user_repo = UserRepo(session)
        await user_repo.set_account_by_id(user_id, data)
    await dialog_manager.switch_to(SelectAccountState.finish)

async def on_account_input(msg: Message, message_input: MessageInput, manager: DialogManager):
    middleware_data: dict[str, Any] = manager.middleware_data
    start_data: dict[str, Any] = manager.start_data

    assert isinstance(middleware_data, dict)
    assert isinstance(start_data, dict)

    session: AsyncSession = middleware_data['session']
    account_name = msg.text
    user_id: int = int(start_data[DialogDataKeys.USER_ID])
    if not account_name:
        await msg.answer(messages.check_input())
        return
    async with session.begin():
        account_repo = AccountRepo(session)
        user_repo = UserRepo(session)
        account = await account_repo.get_by_name(account_name)
        if not account:
            account = Account(name=account_name)
            session.add(account)
            await session.flush()
        await user_repo.set_account_by_id(user_id, account.id)
    if start_data.get(DialogDataKeys.BACK_BTN):
        await manager.switch_to(SelectAccountState.finish)
    else:
        await msg.answer(messages.payin_account_ok())
        await manager.done()
            
select_win = Window(
    Const(messages.select_payin_account(), when='user'),
    Const(messages.user_not_found(), when=~F['user']),
    SwitchTo(
        Const(messages.Buttons.INPUT_PAYIN_ACC), 
        id='aipayinacc', 
        state=SelectAccountState.input_new,
        when='user'
    ),
    ScrollingGroup(
        Select(
            Format('{item.name}'),
            id='accs',
            items='accounts',
            item_id_getter=lambda x: x.id,
            type_factory=int,
            on_click=on_account_click
        ),
        id='accl',
        width=1,
        height=10,
        when='user'
    ),
    state=SelectAccountState.select,
    getter=get_accounts
)

input_win = Window(
    Const(messages.input_payin_account()),
    MessageInput(on_account_input, content_types=ContentType.TEXT),
    state=SelectAccountState.input_new
)

finish_win = Window(
    Const(messages.payin_account_ok()),
    Cancel(Const(messages.Buttons.BACK), when=F['start_data'][DialogDataKeys.BACK_BTN]),
    state=SelectAccountState.finish
)

dialog = Dialog(select_win, input_win, finish_win)

@router.callback_query(UserRegData.filter())
async def user_reg(cbq: CallbackQuery, callback_data: UserRegData, bot: Bot, session: AsyncSession, dialog_manager: DialogManager):
    if not cbq.message:
        await cbq.answer(messages.bad_callback(), show_alert=True)
        return

    await cbq.answer()
    await bot.edit_message_reply_markup(cbq.message.chat.id, cbq.message.message_id, reply_markup=None)

    await dialog_manager.start(
        SelectAccountState.select,
        data={DialogDataKeys.USER_ID: callback_data.user_id},
        mode=StartMode.RESET_STACK,
    )

router.include_router(dialog)
