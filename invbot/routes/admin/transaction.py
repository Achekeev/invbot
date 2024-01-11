import logging
from typing import Any
from enum import StrEnum
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, ContentType, Message
from aiogram.utils.i18n import gettext as _
from aiogram.fsm.state import State, StatesGroup
from aiogram_dialog import Window, Dialog, DialogManager, StartMode, ShowMode
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import Select, ScrollingGroup
from aiogram_dialog.widgets.input import MessageInput
from aiohttp import ClientSession
from ...callbacks import TransactionData, TransactionAction
from ...db import AsyncSession
from ...services import on_tx_accpept, tx_reject_answer, tx_reject
from ...filters import AdminFilter
from ...messages import messages

logger = logging.getLogger(__name__)

router = Router(name=__name__)
router.callback_query.filter(AdminFilter())
router.message.filter(AdminFilter())

class TxDenyState(StatesGroup):
    select_deny_cause = State()
    input_deny_cause = State()

class DialogDataKeys(StrEnum):
    TX_ID   = "tx_id"
    CBQ_ID  = "cbq_id"
    MSG_ID  = "msg_id"
    CHAT_ID = "chat_id"
    EDIT    = "edit"

async def causes_list(**kwargs: Any):
    return {
        "causes": messages.tx_deny_causes()
    }

async def tx_deny_cause_select_handler(event: CallbackQuery, select: Select[int], dialog_manager: DialogManager, data: int):
    bot: Bot = dialog_manager.middleware_data['bot']
    session: AsyncSession = dialog_manager.middleware_data['session']
    tx_id: int = dialog_manager.start_data[DialogDataKeys.TX_ID]
    chat_id: int = dialog_manager.start_data[DialogDataKeys.CHAT_ID]
    cbq_id: str = dialog_manager.start_data[DialogDataKeys.CBQ_ID]
    msg_id: str = dialog_manager.start_data[DialogDataKeys.MSG_ID]
    edit: bool = dialog_manager.start_data[DialogDataKeys.EDIT]

    assert isinstance(bot, Bot)
    assert isinstance(session, AsyncSession)
    assert isinstance(tx_id, int)
    assert isinstance(chat_id, int)
    assert isinstance(cbq_id, str)
    assert isinstance(msg_id, int)
    assert isinstance(edit, bool)

    cause: str|None = next((x[1] for x in messages.tx_deny_causes() if x[0] == data), None)
    if data != 0:
        await tx_reject_answer(tx_id, chat_id, cbq_id, msg_id, bot, session, edit, cause)
        await dialog_manager.done()
    else:
        await dialog_manager.switch_to(TxDenyState.input_deny_cause)

async def tx_deny_custom_cause_handler(msg: Message, message_input: MessageInput, manager: DialogManager):
    logger.info("custom cause handler")
    if not msg.text:
        return
    bot: Bot = manager.middleware_data['bot']
    session: AsyncSession = manager.middleware_data['session']
    tx_id: int = manager.start_data[DialogDataKeys.TX_ID]
    chat_id: int = manager.start_data[DialogDataKeys.CHAT_ID]
    cbq_id: str = manager.start_data[DialogDataKeys.CBQ_ID]
    msg_id: str = manager.start_data[DialogDataKeys.MSG_ID]
    edit: bool = manager.start_data[DialogDataKeys.EDIT]
    assert isinstance(bot, Bot)
    assert isinstance(session, AsyncSession)
    assert isinstance(tx_id, int)
    assert isinstance(chat_id, int)
    assert isinstance(cbq_id, str)
    assert isinstance(msg_id, int)
    assert isinstance(edit, bool)
    await tx_reject_answer(tx_id, chat_id, cbq_id, msg_id, bot, session, edit, msg.text)
    await manager.done()

select_cause_win = Window(
    Const(messages.tx_deny_select_cause()),
    ScrollingGroup(
        Select(
            Format('{item[1]}'),
            id='_tcss',
            items='causes',
            item_id_getter=lambda it: it[0],
            type_factory=int,
            on_click=tx_deny_cause_select_handler
        ),
        id='_tcs',
        width=2,
        height=10,
        hide_on_single_page=True
    ),
    state=TxDenyState.select_deny_cause,
    getter=causes_list
)

input_custom_cause_win = Window(
    Const(messages.tx_deny_input_custom()),
    MessageInput(tx_deny_custom_cause_handler, content_types=ContentType.TEXT),
    state=TxDenyState.input_deny_cause
)

dialog = Dialog(select_cause_win, input_custom_cause_win)

router.include_router(dialog)

@router.callback_query(TransactionData.filter(F.action==TransactionAction.ACCEPT))
async def tx_admin_accept(
    cbq: CallbackQuery, 
    bot: Bot, 
    callback_data: TransactionData, 
    session: AsyncSession, 
    client_session: ClientSession
    ):
    logger.info('callback [admin]: tx_accept, id=%d', callback_data.id)    
    await on_tx_accpept(callback_data.id, cbq, bot, session, client_session)

@router.callback_query(TransactionData.filter(F.action==TransactionAction.DENY))
async def tx_admin_reject(cbq: CallbackQuery, bot: Bot, callback_data: TransactionData, session: AsyncSession, dialog_manager: DialogManager):
    logger.info('callback [admin]: tx_deny, id=%d', callback_data.id)
    if not cbq.message:
        # TODO: show error
        return
    #await cbq.answer(messages.tx_rejected_short())
    tx = await tx_reject(callback_data.id, cbq.message.chat.id, cbq.id, cbq.message.message_id, bot, session, True)
    if tx:
        await dialog_manager.start(
            TxDenyState.select_deny_cause,
            data={
                DialogDataKeys.TX_ID: callback_data.id, 
                DialogDataKeys.MSG_ID: cbq.message.message_id,
                DialogDataKeys.CBQ_ID: cbq.id,
                DialogDataKeys.CHAT_ID: cbq.message.chat.id,
                DialogDataKeys.EDIT: True
            },
            mode=StartMode.NORMAL,
            show_mode=ShowMode.SEND
        )