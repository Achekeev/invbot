import logging
from enum import IntEnum, StrEnum
from typing import Any
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, ContentType
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.i18n import gettext as _
from aiogram_dialog import Window, DialogManager, Dialog, StartMode
from aiogram_dialog.widgets.kbd import Button, Select, ScrollingGroup, SwitchTo, Row
from aiogram_dialog.widgets.text import Const, Multi, Case, Format
from aiogram_dialog.widgets.input import MessageInput
import aiohttp

from ...messages import messages
from ...db import AsyncSession
from ...db.models import User, Transaction
from ...db.repo import TransactionRepo, UserRepo
from ...services import on_tx_accpept, tx_reject
from .transaction import TxDenyState, DialogDataKeys as TxDenyDialogDataKeys
from ...filters import AdminFilter

logger = logging.getLogger(__name__)
router = Router(name=__name__)
router.message.filter(AdminFilter())

class TxFilter(IntEnum):
    ALL       = 0
    PROCESSED = 1

class DialogDataKey(StrEnum):
    TX_TYPE_FILTER = 'tx_type_filter'
    STATUS_FILTER  = 'status_filter'
    USER_ID        = 'user_id'
    USER_NAME      = 'user_name'
    TX_ID          = 'tx_id'

class TxState(StatesGroup):
    list = State()
    info = State()
    id_input = State()

async def on_start(start_data: dict[str, Any], manager: DialogManager):
    dialog_data: dict[str, Any] = manager.dialog_data
    assert isinstance(dialog_data, dict)

    dialog_data[DialogDataKey.TX_TYPE_FILTER] = start_data.get(DialogDataKey.TX_TYPE_FILTER)
    dialog_data[DialogDataKey.STATUS_FILTER] = start_data.get(DialogDataKey.STATUS_FILTER)
    dialog_data[DialogDataKey.USER_ID] = start_data.get(DialogDataKey.USER_ID)

async def get_transactions(dialog_manager: DialogManager, session: AsyncSession, **kwargs: Any):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    middleware_data: dict[str, Any] = dialog_manager.middleware_data
    assert isinstance(dialog_data, dict)
    assert isinstance(middleware_data, dict)

    tx_type: Transaction.TxType | None = dialog_data[DialogDataKey.TX_TYPE_FILTER]
    status_filter: Transaction.Status | None = dialog_data[DialogDataKey.STATUS_FILTER]

    transactions: list[Transaction] = []
    dialog_data[DialogDataKey.TX_ID] = None
    logger.debug('txl: get transactions: %s', status_filter)
    user_id = dialog_data.get(DialogDataKey.USER_ID)
    async with session.begin():
        # get user
        user: User | None = None
        if user_id:
            user_repo = UserRepo(session)
            user = await user_repo.get_by_id(user_id)
        tx_repo = TransactionRepo(session)
        if status_filter is None or status_filter == TxFilter.PROCESSED:
            transactions = list(await tx_repo.get_for_processing(
                user_id=dialog_data.get(DialogDataKey.USER_ID)
            ))
        else:
            transactions = list(await tx_repo.get_all(
                tx_type=tx_type, 
                user_id=dialog_data.get(DialogDataKey.USER_ID)
            ))
    return {'transactions': transactions, 'user': user}

async def get_transaction(dialog_manager: DialogManager, user: User | None, session: AsyncSession, **kwargs: Any):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    start_data: dict[str, Any] = dialog_manager.start_data

    start_tx_id: int | None = start_data.get(DialogDataKey.TX_ID)
    tx_id: int | None = start_tx_id or dialog_data.get(DialogDataKey.TX_ID)
    start_data[DialogDataKey.TX_ID] = None
    tx: Transaction | None = None

    if tx_id:
        async with session.begin():
            tx_repo = TransactionRepo(session)
            tx = await tx_repo.get_by_id(tx_id, related=True)
    return {
        'tx': tx, 
        'tx_text': messages.tx_info(tx) if tx else 'Транзакция не найдена', 
        'back_btn': start_tx_id is None
    }

async def on_tx_type_all_click(event: CallbackQuery, button: Button, dialog_manager: DialogManager, data: Any):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    assert isinstance(dialog_data, dict)

    dialog_data[DialogDataKey.TX_TYPE_FILTER] = None


async def on_tx_type_payin_click(event: CallbackQuery, button: Button, dialog_manager: DialogManager, data: Any):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    assert isinstance(dialog_data, dict)

    dialog_data[DialogDataKey.TX_TYPE_FILTER] = Transaction.TxType.PAYIN

async def on_tx_type_payout_click(event: CallbackQuery, button: Button, dialog_manager: DialogManager, data: Any):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    assert isinstance(dialog_data, dict)

    dialog_data[DialogDataKey.TX_TYPE_FILTER] = Transaction.TxType.PAYOUT
    
async def on_tx_status_process_click(event: CallbackQuery, button: Button, dialog_manager: DialogManager):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    dialog_data[DialogDataKey.STATUS_FILTER] = TxFilter.PROCESSED

async def on_tx_status_all_click(event: CallbackQuery, button: Button, dialog_manager: DialogManager):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    dialog_data[DialogDataKey.STATUS_FILTER] = TxFilter.ALL

async def on_tx_click(event: CallbackQuery, select: Select[int], dialog_manager: DialogManager, data: int):
    # middleware_data: dict[str, Any] = dialog_manager.middleware_data
    # session: AsyncSession = middleware_data['session']
    # async with session.begin():
    #     tx_repo = TransactionRepo(session)
    #     tx = await tx_repo.get_by_id(data)
    # if not tx:
    #     await event.answer(messages.tx_not_found(), show_alert=True)
    #     return
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    dialog_data[DialogDataKey.TX_ID] = data
    return await dialog_manager.switch_to(TxState.info)

async def on_reject_click(event: CallbackQuery, button: Button, dialog_manager: DialogManager):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    middleware_data: dict[str, Any] = dialog_manager.middleware_data

    tx_id: int | None = dialog_data[DialogDataKey.TX_ID]
    if not tx_id:
        await event.answer(messages.tx_not_found(), show_alert=True)
        return
    session: AsyncSession = middleware_data['session']
    bot: Bot = middleware_data['bot']

    assert isinstance(session, AsyncSession)
    chat_id: int|None = None
    msg_id: int|None = None
    if event.message is not None:
        chat_id = event.message.chat.id
        msg_id = event.message.message_id
    tx: Transaction | None = await tx_reject(tx_id, chat_id, event.id, msg_id, bot, session, False)
    if tx:
        await dialog_manager.start(
            TxDenyState.select_deny_cause,
            data={
                TxDenyDialogDataKeys.TX_ID: tx_id, 
                TxDenyDialogDataKeys.MSG_ID: msg_id,
                TxDenyDialogDataKeys.CBQ_ID: event.id,
                TxDenyDialogDataKeys.CHAT_ID: chat_id,
                TxDenyDialogDataKeys.EDIT: False
            },
        )
    # if tx:
    #     await tx_reject_answer(tx_id, chat_id, event.id, msg_id, bot, session, edit=False)

async def on_accept_click(event: CallbackQuery, button: Button, dialog_manager: DialogManager):
    dialog_data: dict[str, Any] = dialog_manager.dialog_data
    middleware_data: dict[str, Any] = dialog_manager.middleware_data

    tx_id: int | None = dialog_data[DialogDataKey.TX_ID]
    if not tx_id:
        await event.answer(_('Транзакция не выбрана'), show_alert=True)
        return
    session: AsyncSession = middleware_data['session']
    client_session: aiohttp.ClientSession = middleware_data['client_session']
    bot: Bot = middleware_data['bot']
    
    await on_tx_accpept(tx_id, event, bot, session, client_session, edit=False)

async def search_handler(msg: Message, message_input: MessageInput, manager: DialogManager):
    if not msg.text:
        await msg.answer('Проверте правильность ввода ID транзакции и введите его заново')
        return
    try:
        tx_id: int = int(msg.text)
    except (ValueError, TypeError):
        await msg.answer('Проверте правильность ввода ID транзакции и введите его заново')
        return
    manager.dialog_data[DialogDataKey.TX_ID] = tx_id
    await manager.switch_to(TxState.info)    

tx_list_win = Window(
    Const('Список транзакций', when=~F['user']),
    Format('Список транзакций пользователя {user.username} {user.phone_number}', when=F['user']),
    Multi(
        Const('Тип: '),
        Case(
            {
                Transaction.TxType.PAYIN: Const('PAY-IN'),
                Transaction.TxType.PAYOUT: Const('PAY-OUT'),
                ...: Const('Все')
            },
            selector='dialog_data[tx_type_filter]'
        ),
        sep=' '
    ),
    Multi(
        Const('Статус: '),
        Case(
            {
                TxFilter.ALL: Const('Все'),
                TxFilter.PROCESSED: Const('К обработке'),
                ...: Const('К обработке')
            },
            selector=F['dialog_data']['status_filter']
        ),
        sep=' '
    ),
    ScrollingGroup(
        Select(
            Format('{item.tx_type_sym}[{item.id}] ID: {item.ext.ext}: {item.amount} {item.currency} : {item.status_text}'),
            id='txt',
            items='transactions',
            item_id_getter=lambda x: x.id,
            type_factory=int,
            on_click=on_tx_click
        ),
        id='txl',
        width=1,
        height=10
    ),
    Row(
        Button(Const('Все'), id='txfa', on_click=on_tx_status_all_click),
        Button(Const('К обработке'), id='txfp', on_click=on_tx_status_process_click)
    ),

    state=TxState.list,
    getter=get_transactions,
)

tx_info_win = Window(
    Format('{tx_text}'),
    Row(
        Button(Const(messages.Buttons.ACCEPT), id='txacc', when=F['tx'].can_accept, on_click=on_accept_click),
        Button(Const(messages.Buttons.DENY), id='txdny', when=F['tx'].can_deny, on_click=on_reject_click),
        when=F['tx']
    ),
    SwitchTo(Const('К списку транзакций'), id='txback', state=TxState.list, when=F['back_btn']),
    state=TxState.info,
    getter=get_transaction
)

tx_id_input_win = Window(
    Const('Введите ID транзакции'),
    MessageInput(search_handler, content_types=ContentType.TEXT),
    state=TxState.id_input
)

async def txl_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager, session: AsyncSession):
    logger.info('ccommand [admin]: txl')
    await dialog_manager.start(
        TxState.list,
        mode=StartMode.RESET_STACK,
        data={},
    )

async def tx_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager, command: CommandObject):
    logger.info('command [admin]: tx %s', command.args)
    start_state = TxState.id_input
    tx_id: int = 0
    tx_id_str: str | None = command.args
    if tx_id_str:
        try:
            tx_id = int(tx_id_str)
            start_state = TxState.info
        except (ValueError, TypeError):
            pass
    await dialog_manager.start(
        start_state,
        data={DialogDataKey.TX_ID: tx_id},
        mode=StartMode.RESET_STACK
    )

dialog = Dialog(tx_list_win, tx_info_win, on_start=on_start)

router.include_router(dialog)