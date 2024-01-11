import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardMarkup
import aiohttp
from aiohttp import ClientSession
from .db import AsyncSession
from .db.models import Transaction
from .db.repo import TransactionRepo
from .bithide import api as bithide
from .tools import utc_now
from .messages import messages
import settings

logger = logging.getLogger(__name__)

async def tx_accept_admin(tx: Transaction, session: AsyncSession, client_session: ClientSession):
    tx.admin_action_at = utc_now()
    tx.status = Transaction.Status.ADMIN_ACCEPTED

    if tx.tx_type == Transaction.TxType.PAYOUT and settings.BITHIDE_AUTO_PAYOUT:
        await payout_crypto(tx, session, client_session)
    
async def get_address(client_session: ClientSession, ext: str, currency: str, amount: float) -> str | None:
    try:
        status, data = await bithide.get_address(client_session, ext, currency, amount)
    except (aiohttp.ClientError) as ex:
        logger.error(ex)
        return None
    if status == 200 and data and data.get('Status') == bithide.Status.SUCCESS:
        return data.get('Address')

async def payout_crypto(tx: Transaction, session: AsyncSession, client_session: ClientSession):
    status, data = await bithide.withdraw(client_session, tx)

    if status == 200 and data and data.get('Status') == bithide.Status.SUCCESS:
        tx.status = Transaction.Status.GW_SEND
        return

    if not data:
        tx.status = Transaction.Status.GW_ERROR
        return

    tx.gw_error = data.get('ErrorCode')

    if status != 200:
        tx.status = Transaction.Status.GW_ERROR
    else:
        tx.status = Transaction.Status.GW_REJECTED

async def on_tx_accpept(tx_id: int, 
                        cbq: CallbackQuery, 
                        bot: Bot, 
                        session: AsyncSession, 
                        client_session: aiohttp.ClientSession,
                        edit: bool = True
                        ):
    error_msg: str | None = None
    no_op: bool = False
    async with session.begin():
        tx_repo = TransactionRepo(session)
        tx = await tx_repo.get_by_id(tx_id, related=True, for_update=True)
        if tx:
            if tx.can_accept:
                try:
                    await tx_accept_admin(tx, session, client_session)
                except aiohttp.ClientError as ex:
                    logger.error(ex)
                    tx.status = Transaction.Status.GW_ERROR
                    error_msg = messages.http_error()    
                except Exception as ex:
                    logger.exception(ex)
                    tx.status = Transaction.Status.GW_ERROR                
                    error_msg = messages.common_error()
                # finally:
                #     await session.flush()                
                #     tx = await tx_repo.get_by_id(tx.id, related=True)
            else:
                no_op = True
    if not tx:
        await cbq.answer(messages.tx_not_found(), show_alert=True)
        if cbq.message and edit:
            await cbq.message.delete()
        return

    if no_op:
        await cbq.answer(messages.tx_cant_accepted(), show_alert=True)
        if cbq.message and edit:
            await cbq.message.edit_text(
                messages.tx_info(tx), 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
            )
        return

    if tx.is_error and not error_msg:
        error_msg = messages.tx_error_cb()
        
    if error_msg:
        await cbq.answer(error_msg, show_alert=True)
        if cbq.message and edit:
            if tx.tx_type is not Transaction.TxType.PAYIN:
                await cbq.message.edit_caption(
                    caption=messages.tx_rejected(tx) if tx.status == Transaction.Status.GW_REJECTED else messages.tx_error(tx), 
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
                )
            else:
                await cbq.message.edit_text(
                    messages.tx_rejected(tx) if tx.status == Transaction.Status.GW_REJECTED else messages.tx_error(tx), 
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
                )
        await bot.send_message(tx.user.chat_id, messages.tx_error(tx, full=False))
        return

    if cbq.message and edit: 
        if tx.tx_type is not Transaction.TxType.PAYIN:
            await cbq.message.edit_caption(caption=messages.tx_accepted(tx), reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))
        else:
            await cbq.message.edit_text(messages.tx_accepted(tx), reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))

    await bot.send_message(tx.user.chat_id, messages.tx_accepted(tx, full=False))

async def tx_reject(tx_id: int, chat_id: int|None, cbq_id: str, msg_id: int|None, bot: Bot, session: AsyncSession, edit: bool = True) -> Transaction|None:
    no_op: bool = False
    async with session.begin():
        tx_repo = TransactionRepo(session)
        tx = await tx_repo.get_by_id(tx_id, related=True, for_update=True)
        if tx:
            if tx.can_deny:
                tx.status = Transaction.Status.ADMIN_REJECTED
                await session.flush()
                await session.refresh(tx)
            else:
                no_op = True
    if not tx:
        await bot.answer_callback_query(cbq_id, messages.tx_not_found(), show_alert=True)
        if msg_id and chat_id and edit:
            await bot.delete_message(chat_id, msg_id)
        return None

    if no_op:
        await bot.answer_callback_query(cbq_id, messages.tx_cant_deny(), show_alert=True)
        if msg_id and chat_id and edit:
            if tx.tx_type is not Transaction.TxType.PAYIN:
                await bot.edit_message_caption(
                    chat_id, msg_id, 
                    caption=messages.tx_info(tx), 
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
                )
            else:
                await bot.edit_message_text(messages.tx_info(tx), chat_id, msg_id)
        return None
    await bot.answer_callback_query(cbq_id, messages.tx_rejected_short())
    return tx

async def tx_reject_answer(tx_id: int, chat_id: int|None, cbq_id: str, msg_id: int|None, bot: Bot, session: AsyncSession, edit: bool = True, cause: str|None = None):
    async with session.begin():
        tx_repo = TransactionRepo(session)
        tx = await tx_repo.get_by_id(tx_id, related=True, for_update=True)
        if tx:
            tx.reject_cause = cause
            await session.flush()
            await session.refresh(tx)                        
        else:
            return
    try:
        if msg_id and chat_id and edit:
            if tx.tx_type is not Transaction.TxType.PAYIN:
                await bot.edit_message_caption(
                    chat_id, msg_id,
                    caption=messages.tx_rejected(tx), 
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
                )
            else:
                await bot.edit_message_text(messages.tx_rejected(tx), chat_id, msg_id, reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))
        await bot.send_message(tx.user.chat_id, messages.tx_rejected(tx, full=False))
    except TelegramAPIError as ex:
        logger.exception(ex)
