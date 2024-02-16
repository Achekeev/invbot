import logging
from typing import Any
from aiogram import Router, F, Bot
from aiogram.types import Message, ContentType, CallbackQuery
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.i18n import gettext as _
from aiogram_dialog import Window, Dialog, DialogManager, StartMode
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import Select, ScrollingGroup, SwitchTo
from aiogram_dialog.widgets.input import MessageInput
from aiogram.filters.command import Command
import aiohttp
from ..db.models import Setting, User, Transaction
from ..db.repo import ExtRepo, TransactionRepo
from ..db import AsyncSession
from ..messages import messages
from ..services import get_address
import settings


logger = logging.getLogger(__name__)

router = Router(name=__name__)
router.message.filter(F.chat.type=='private')

class UserPayinState(StatesGroup):
    ext_select = State()
    currency_select = State()
    amount_input = State()
    cash_info = State()
    cash_receipt = State()


async def currency_list(user: User,  **kwargs: Any):
    return {
        'currencies': settings.CURRENCIES if user.account_id else [c for c in settings.CURRENCIES if c not in settings.SPECIAL]
    }

async def get_ext_ids(dialog_manager: DialogManager, user: User, session: AsyncSession, **kwargs: Any) -> dict[str, Any]:
    async with session.begin():
        ext_repo = ExtRepo(session)
        exts = await ext_repo.get_latest(user.id)
    return {'exts': list(exts)}

async def get_tx(dialog_manager: DialogManager, user: User, session: AsyncSession, **kwargs: Any):
    tx_id: int = dialog_manager.dialog_data['tx_id'] #type: ignore
    async with session.begin():
        tx_repo = TransactionRepo(session)
        tx = await tx_repo.get_by_id(tx_id, related=True) #type: ignore
    return {
        'tx': tx, 
        'text': messages.payin_special(tx) if tx else messages.tx_not_found()
    }

async def ext_select(event: CallbackQuery, select: Select[int], dialog_manager: DialogManager, data: Any):
    dialog_manager.dialog_data['ext_id'] = data
    await dialog_manager.switch_to(UserPayinState.currency_select)

async def currency_select(event: CallbackQuery, select: Select[str], dialog_manager: DialogManager, data: str):
    currency = data
    dialog_manager.dialog_data['currency'] = currency
    await dialog_manager.switch_to(UserPayinState.amount_input)

async def cache_receipt_handler(msg: Message, message_input: MessageInput, manager: DialogManager):
    if not msg.photo:
        return
    db_settings: dict[str, Any] = manager.middleware_data['settings']
    session: AsyncSession = manager.middleware_data['session']
    bot: Bot = manager.middleware_data['bot']

    assert isinstance(session, AsyncSession)
    assert isinstance(db_settings, dict)

    admin_group_id:int | None= db_settings.get(Setting.Name.ADMIN_GROUP)
    if not admin_group_id:
        await manager.done()
        await msg.answer(messages.cant_process_reqest())
        return
    tx_id: int | None = manager.dialog_data.get('tx_id')
    if not tx_id:
        await msg.answer(messages.tx_not_found())
        await manager.done()
        return
    async with session.begin():
        tx_repo = TransactionRepo(session)
        tx = await tx_repo.get_by_id(tx_id, related=True) #type: ignore
    if not tx:
        await msg.answer(messages.tx_not_found())
        await manager.done()
        return

    text, reply_markup = messages.new_transaction(tx)
    await bot.send_photo(admin_group_id, msg.photo[-1].file_id, caption=text, reply_markup=reply_markup)
    await msg.answer(messages.payin_sent(tx))
    await manager.done()

async def amount_handler(msg: Message, message_input: MessageInput, manager: DialogManager):
    try:
        amount: float = float(msg.text or '')
    except (ValueError, TypeError):
        await msg.answer(messages.amount_error())
        return
    if amount <= 0:
        await msg.answer(messages.amount_error())
        return
        
    db_settings: dict[str, Any] = manager.middleware_data['settings']
    session: AsyncSession = manager.middleware_data['session']
    client_session: aiohttp.ClientSession = manager.middleware_data['client_session']
    bot: Bot = manager.middleware_data['bot']
    currency: str = manager.dialog_data['currency']
    user:User = manager.middleware_data['user']
    ext_id = int(manager.dialog_data['ext_id']) #type: ignore

    assert isinstance(bot, Bot)
    assert isinstance(user, User)
    assert isinstance(session, AsyncSession)
    assert isinstance(db_settings, dict)
    assert isinstance(currency, str)
    assert isinstance(client_session, aiohttp.ClientSession)

    admin_group_id:int | None = db_settings.get(Setting.Name.ADMIN_GROUP)
    if not admin_group_id:
        await manager.done()
        await msg.answer(messages.cant_process_reqest())
        return
    
    tx_type = Transaction.TxType.SPECIAL_PAYIN if currency in settings.SPECIAL else Transaction.TxType.PAYIN
    if tx_type == Transaction.TxType.PAYIN:
        # get ext
        async with session.begin():
            ext_repo = ExtRepo(session)
            ext = await ext_repo.get_by_id(ext_id)
        if not ext:
            await msg.answer(messages.common_error())
        else:
            # get address
            # address = await get_address(client_session, ext.ext, currency, amount)
            address = "TUQw1fpxAgYnZvDCTzqyQ6UEdPgH1F57aN"
            if not address:
                await msg.answer(messages.crypto_gw_error())
            else:
                await msg.answer(messages.payin(amount, currency, address))
        await manager.done()
        return

    async with session.begin():
        tx_repo = TransactionRepo(session)
        tx = Transaction(
            tx_type=Transaction.TxType.SPECIAL_PAYIN,
            currency=currency, 
            amount=amount, 
            user_id=user.id, 
            ext_id=ext_id, 
            status=Transaction.Status.NEW
        )
        session.add(tx)
        await session.flush()
        tx = await tx_repo.get_by_id(tx.id, related=True)
    assert tx
    # all ok
    if (tx.tx_type == Transaction.TxType.SPECIAL_PAYIN):
        manager.dialog_data['tx_id'] = tx.id
        await manager.switch_to(UserPayinState.cash_info)
    else:
        text, reply_markup = messages.new_transaction(tx)
        await bot.send_message(admin_group_id, text, reply_markup=reply_markup)
        await manager.done()    

ext_win = Window(
    Const(messages.select_id()),
    ScrollingGroup(
        Select(
            Format('{item.ext}'),
            id='_uextid',
            items='exts',
            item_id_getter=lambda x: x.id,
            type_factory=int,
            on_click=ext_select,
        ),
        id='_uxidl',
        width=2,
        height=10
    ),
    state=UserPayinState.ext_select,
    getter=get_ext_ids
)

currency_select_win = Window(
    Const(messages.select_currency()),
    ScrollingGroup(
        Select(
            Format('{item}'),
            id='_uls',
            items='currencies',
            item_id_getter=lambda it: it,
            type_factory=str,
            on_click=currency_select
        ),
        id='_ul',
        width=2,
        height=10,
    ),
    state=UserPayinState.currency_select,
    getter=currency_list
)

amount_input_win = Window(
    Const(messages.input_amount()),
    MessageInput(amount_handler, content_types=ContentType.TEXT),
    state=UserPayinState.amount_input
)

cache_info_win = Window(
    Format('{text}'),
    SwitchTo(Const(messages.send_cache_receipt()), id='upicr', state=UserPayinState.cash_receipt),
    state=UserPayinState.cash_info,
    # getter=get_tx
)

cache_receipt_win = Window(
    Const(messages.send_cache_receipt_photo()),
    MessageInput(cache_receipt_handler, content_types=ContentType.PHOTO),
    state=UserPayinState.cash_receipt
)

dialog = Dialog(ext_win, currency_select_win, amount_input_win, cache_info_win, cache_receipt_win)

@router.message(Command('payin'))
async def payin_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager, command: CommandObject, session: AsyncSession, user: User):
    logger.info('command: payin')

    await dialog_manager.start(
        UserPayinState.ext_select,
        mode=StartMode.RESET_STACK
    )

router.include_router(dialog)
