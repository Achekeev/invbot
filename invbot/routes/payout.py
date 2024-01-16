import logging
from typing import Any
from aiogram import Router, F, Bot
from aiogram.types import Message, ContentType, CallbackQuery
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.i18n import gettext as _
from aiogram.exceptions import TelegramMigrateToChat
from aiogram_dialog import Window, Dialog, DialogManager, StartMode
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import Select, ScrollingGroup, Checkbox
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


class UserPayoutState(StatesGroup):
    ext_select = State()
    currency_select = State()
    amount_input = State()
    tip_input = State()
    wallet_address = State()
    account_screen = State()

async def currency_list(user: User,  **kwargs: Any):
    return {
        'currencies': settings.CURRENCIES if user.account_id else [c for c in settings.CURRENCIES if c not in settings.SPECIAL]
    }

async def get_ext_ids(dialog_manager: DialogManager, user: User, session: AsyncSession, **kwargs: Any) -> dict[str, Any]:
    async with session.begin():
        ext_repo = ExtRepo(session)
        exts = await ext_repo.get_latest(user.id)
    return {'exts': list(exts)}

async def ext_select(event: CallbackQuery, select: Select[int], dialog_manager: DialogManager, data: Any):
    dialog_manager.dialog_data['ext_id']  = data
    await dialog_manager.switch_to(UserPayoutState.currency_select)

async def currency_select(event: CallbackQuery, select: Select[str], dialog_manager: DialogManager, data: Any):
    currency = data
    dialog_manager.dialog_data['currency'] = currency
    await dialog_manager.switch_to(UserPayoutState.account_screen)

async def account_screen_handler(msg: Message, message_input: MessageInput, manager: DialogManager):
    if not msg.photo:
        return
    manager.dialog_data['account_screen'] = msg.photo[-1].file_id
    await manager.switch_to(UserPayoutState.amount_input)

async def amount_handler(msg: Message, message_input: MessageInput, manager: DialogManager):
    try:
        amount: float = float(msg.text or '')
    except (ValueError, TypeError):
        await msg.answer(messages.amount_error())
        return
    if amount <= 0:
        await msg.answer(messages.amount_error())
        return
    manager.dialog_data['amount'] = amount
    if manager.find('_ulstip').is_checked(): #type: ignore
        await manager.switch_to(UserPayoutState.tip_input)
    else:
        await manager.switch_to(UserPayoutState.wallet_address)

async def tip_handler(msg: Message, message_input: MessageInput, manager: DialogManager):
    try:
        tip_amount: float = float(msg.text or '')
    except (ValueError, TypeError):
        await msg.answer(messages.amount_error())
        return
    if tip_amount <= 0:
        await msg.answer(messages.amount_error())
        return
    manager.dialog_data['tip'] = tip_amount
    await manager.switch_to(UserPayoutState.wallet_address)

async def payout_handler(msg: Message, message_input: MessageInput, manager: DialogManager):
    if not msg.text:
        await msg.answer(_('Введите адрес кошелька'))
        return
    wallet_address: str = msg.text.strip()
    if not wallet_address:
        await msg.answer(_('Введите адрес кошелька'))
        return

    db_settings: dict[str, Any] = manager.middleware_data['settings']
    session: AsyncSession = manager.middleware_data['session']
    client_session: aiohttp.ClientSession = manager.middleware_data['client_session']
    bot: Bot = manager.middleware_data['bot']
    currency: str = manager.dialog_data['currency']
    user:User = manager.middleware_data['user']
    ext_id = int(manager.dialog_data['ext_id']) #type: ignore
    amount: float = float(manager.dialog_data['amount']) #type: ignore
    payout_tip: float = float(manager.dialog_data.get('tip') or 0.0) #type: ignore

    assert isinstance(bot, Bot)
    assert isinstance(user, User)
    assert isinstance(session, AsyncSession)
    assert isinstance(db_settings, dict)
    assert isinstance(currency, str)
    assert isinstance(client_session, aiohttp.ClientSession)

    admin_group_id:int | None= db_settings.get(Setting.Name.ADMIN_GROUP)
    if not admin_group_id:
        await manager.done()
        await msg.answer(messages.cant_process_reqest())
        return

    bithide_address: str | None = None
    tx_type = Transaction.TxType.SPECIAL_PAYOUT if currency in settings.SPECIAL else Transaction.TxType.PAYOUT
    if tx_type == Transaction.TxType.PAYOUT:
        # get ext
        async with session.begin():
            ext_repo = ExtRepo(session)
            ext = await ext_repo.get_by_id(ext_id)

        if not ext:
            await msg.answer(messages.common_error())
            await manager.done()
            return

        # get address
        bithide_address = await get_address(client_session, ext.ext, currency, amount)
        if not bithide_address:
            await msg.answer(messages.crypto_gw_error())
            await manager.done()
            return
    async with session.begin():
        tx_repo = TransactionRepo(session)
        tx = Transaction(
            tx_type=tx_type,
            currency=currency, 
            amount=amount, 
            payout_tip=payout_tip,
            user_id=user.id, 
            ext_id=ext_id, 
            status=Transaction.Status.NEW,
            payout_src_address=bithide_address,
            payout_dst_address=wallet_address
        )
        session.add(tx)
        await session.flush()
        tx = await tx_repo.get_by_id(tx.id, related=True)
        assert tx
    if tx.tx_type == Transaction.TxType.SPECIAL_PAYOUT:
        await msg.answer(messages.payout_special(tx))
    else:
        await msg.answer(messages.payout(tx))
    text, reply_markup = messages.new_transaction(tx)
    try:
        photo_id: str = manager.dialog_data.get('account_screen') #type: ignore
        await bot.send_photo(admin_group_id, photo_id, caption=text, reply_markup=reply_markup)
    except TelegramMigrateToChat as ex:
        logger.info('new chat id=%d', ex.migrate_to_chat_id)
    await manager.done()


ext_win = Window(
    Const('Выберите ID'),
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
    state=UserPayoutState.ext_select,
    getter=get_ext_ids
)

currency_select_win = Window(
    Const(messages.payout_select_currency()),
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
        hide_on_single_page=True
    ),
    Checkbox(
        Const(messages.payout_tip(True)), 
        Const(messages.payout_tip(False)), 
        id='_ulstip',
        default=False
    ),
    state=UserPayoutState.currency_select,
    getter=currency_list
)

amount_input_win = Window(
    Const('Введите сумму'),
    MessageInput(amount_handler, content_types=ContentType.TEXT),
    state=UserPayoutState.amount_input
)

tip_input_win = Window(
    Const('Введите сумму чаевых'),
    MessageInput(tip_handler, content_types=ContentType.TEXT),
    state=UserPayoutState.tip_input
)

wallet_address_win = Window(
    Const('Введите адрес кошелька'),
    MessageInput(payout_handler, content_types=ContentType.TEXT),
    state=UserPayoutState.wallet_address
)

account_screen_win = Window(
    Const(messages.send_account_screen()),
    MessageInput(account_screen_handler, content_types=ContentType.PHOTO),
    state=UserPayoutState.account_screen
)

dialog = Dialog(ext_win, currency_select_win, account_screen_win, amount_input_win, tip_input_win, wallet_address_win)

@router.message(Command('payin'))
async def payout_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager, command: CommandObject, session: AsyncSession, user: User):
    # if dialog_manager.has_context():
    #     await dialog_manager.done()
    logger.info('command: payout')

    # await state.clear()
    # if not user.account_id:
    #     await msg.answer(messages.no_pay())
    #     return

    await dialog_manager.start(
        UserPayoutState.ext_select,
        mode=StartMode.RESET_STACK
    )

router.include_router(dialog)
