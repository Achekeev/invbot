import logging
from typing import Any
from enum import StrEnum
from aiogram import Router, F
from aiogram.types import Message, ContentType, CallbackQuery
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.i18n import gettext as _
from aiogram_dialog import Window, Dialog, DialogManager, StartMode
from aiogram_dialog.widgets.text import Const, Format, Multi
from aiogram_dialog.widgets.kbd import Row, Button, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.input import MessageInput
from ...db.models import User
from ...db.repo import UserRepo
from ...db import AsyncSession
from ...messages import messages
from ...filters import AdminFilter
from . import set_account, transaction_dialog

logger = logging.getLogger(__name__)
router = Router(name=__name__)
router.message.filter(AdminFilter())
#router.callback_query.filter(AdminFilter())

class DialogKey(StrEnum):
    SEARCH = 'search'
    USER_ID = 'user_id'

class UserDialogState(StatesGroup):
    search = State()
    list = State()
    info = State()
    user_ext_id = State()


async def get_users(dialog_manager: DialogManager, user: User | None, session: AsyncSession, **kwargs: Any) -> dict[str, Any]:
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    middleware_data: dict[str, Any] = dialog_manager.middleware_data
    assert isinstance(dialog_data, dict)
    assert isinstance(middleware_data, dict)

    async with session.begin():
        user_repo = UserRepo(session)
        users = list(await user_repo.get_without_account())
    logger.info('got users without payin accounts: %d', len(users))
    return {'users': users}

async def get_user_info(dialog_manager: DialogManager, session: AsyncSession, **kwargs: Any) -> dict[str, Any]:
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    start_data: dict[str, Any] = dialog_manager.start_data
    assert isinstance(dialog_data, dict)
    assert isinstance(start_data, dict)

    user_id: int | None = dialog_data.get(DialogKey.USER_ID)
    search_str: str | None = start_data.get(DialogKey.SEARCH) or dialog_data.get(DialogKey.SEARCH)
    user: User | None = None
    async with session.begin():
        user_repo = UserRepo(session)
        if user_id is not None:
            user = await user_repo.get_by_id(user_id, related=True)
        elif search_str is not None:
            # try search by id
            user = await user_repo.get_by_ext(search_str, related=True)
            if not user:
                # try to search by phone
                user = await user_repo.get_by_phone_number(search_str, related=True)
    if not user:
        return {'user': None}
    #user_dict = user.as_dict()
    dialog_data[DialogKey.USER_ID] = user.id
    return {'user': user}

async def search_handler(msg: Message, message_input: MessageInput, manager: DialogManager):
    manager.dialog_data[DialogKey.SEARCH] = msg.text or ''
    await manager.switch_to(UserDialogState.info)

async def on_txl_click(event: CallbackQuery, button: Button, dialog_manager: DialogManager):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    assert isinstance(dialog_data, dict)
    user_id: int = dialog_data[DialogKey.USER_ID]
    await dialog_manager.start(
        transaction_dialog.TxState.list,
        data={transaction_dialog.DialogDataKey.USER_ID: user_id, },
        mode=StartMode.RESET_STACK
    )

async def on_user_click(event: CallbackQuery, select: Select[int], dialog_manager: DialogManager, data: int):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    dialog_data[DialogKey.USER_ID] = data
    await dialog_manager.switch_to(UserDialogState.info)

async def on_payin_click(event: CallbackQuery, button: Button, dialog_manager: DialogManager):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    assert isinstance(dialog_data, dict)
    user_id: int = dialog_data[DialogKey.USER_ID]
    await dialog_manager.start(
        set_account.SelectAccountState.select,
        data={
            set_account.DialogDataKeys.USER_ID: user_id, 
            set_account.DialogDataKeys.BACK_BTN: True
        },
        mode=StartMode.NORMAL
    )

user_list_win = Window(
    Const('Список пользователей без данных для пополнения'),
    Const('<b>Пользователей нет</b>', when=~F['users']),
    ScrollingGroup(
        Select(
            Format('[{item.id}] {item.username}, {item.phone_number}'),
            id='uslg',
            items='users',
            item_id_getter=lambda x: x.id,
            type_factory=int,
            on_click=on_user_click
        ),
        id='uslr',
        width=1,
        height=10,
        when=F['users']
    ),
    state=UserDialogState.list,
    getter=get_users
)

user_info_win = Window(
    Const('Пользователь не найден', when=~F['user']),
    Multi(
        Format('Ник: {user.username}, тел.: {user.phone_number}'),
        Format('{user.last_name} {user.first_name}'),
        Format('Payin: {user.account_name}'),
        Format('Последний визит: {user.last_visited_text}'),
        when=F['user']
    ),
    Row(
        Button(
            Const('Транзакции'), 
            id='_autxl',
            on_click=on_txl_click
        ),
        Button(
            Const('Payin аккаунт'), 
            id='_autpayin',
            on_click=on_payin_click
        ),
        when=F['user']
    ),
    SwitchTo(Const(messages.Buttons.BACK), id='_aul', state=UserDialogState.list, when=F['dialog_data'][DialogKey.USER_ID]),
    state=UserDialogState.info,
    getter=get_user_info
)

search_win = Window(
    Const(messages.search_id_phone()),
    MessageInput(search_handler, content_types=ContentType.TEXT),
    state=UserDialogState.search
)

dialog = Dialog(user_list_win, user_info_win, search_win)

#@router.message(Command('id'))
async def id_cmd(msg: Message, dialog_manager: DialogManager, command: CommandObject, state: FSMContext):
    logger.info('command [admin]: id')        
    await dialog_manager.start(
        UserDialogState.info if command.args else UserDialogState.search, 
        data={DialogKey.SEARCH: command.args},
        mode=StartMode.RESET_STACK
    )


async def regs_cmd(msg: Message, dialog_manager: DialogManager, session: AsyncSession):
    logger.info('command [admin]: regs')    
    await dialog_manager.start(
        state=UserDialogState.list,
        data={},
        mode=StartMode.RESET_STACK
    )

router.include_router(dialog)
