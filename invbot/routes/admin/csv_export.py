import logging
import os
import csv
import aiofiles
from datetime import datetime, timedelta, UTC
from aiocsv.writers import AsyncWriter
from aiogram import Router, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.i18n import gettext as _
from aiogram_dialog import DialogManager
from sqlalchemy.ext.asyncio import AsyncResult
from ...db import AsyncSession
from ...db.repo import UserRepo, TransactionRepo
from ...db.models  import Transaction
from ...filters import AdminFilter

logger = logging.getLogger(__name__)
router = Router(name=__name__)
router.message.filter(AdminFilter())

#TODO: set encoding in settings
async def users_export_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager, session: AsyncSession):
    await dialog_manager.reset_stack()
    await state.clear()

    fname: str | None = None
    try:
        async with aiofiles.tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False) as afp:
            fname = str(afp.name)
            writer = AsyncWriter(afp, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            await writer.writerow([
                'DBID', 'phone', 'tg_user_id', 'ID', 'bcast_status', 'last_visited', 
                'tg_username', 'fist_name', 'last_name'
            ])
            async with session.begin():
                user_repo = UserRepo(session)
                users = await user_repo.get_all_stream(with_exts=True)
                users.unique()
                async for row in users:
                    user = row[0]
                    for ext in user.exts:
                        await writer.writerow([
                            user.id, f"'{user.phone_number}", 
                            user.user_id, ext.ext, user.bcast_status, user.last_visited_text,
                            user.username, user.first_name, user.last_name
                        ])
            logger.info(f'save users into temp file: {fname}')
        fs_file = FSInputFile(fname, filename=f'users_{datetime.now().isoformat()}.csv')
        await msg.answer_document(fs_file)
    except IOError as ex:
        logger.error("can't created user export file: %s", ex)
    finally:
        if fname is not None:
            os.unlink(fname)

class TxExportState(StatesGroup):
    start_date = State()
    stop_date = State()

TODAY_TEXT = 'now'
YESTERDAY_TEXT = 'yesterday'

async def tx_export(filename: str, txs: AsyncResult[tuple[Transaction]]) -> FSInputFile|None:
    fname: str | None = None
    try: 
        async with aiofiles.tempfile.NamedTemporaryFile(
            'w', encoding='utf-8', newline='', delete=False
        ) as afp:
            fname = str(afp.name)
            writer = AsyncWriter(afp, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            await writer.writerow([
                'DBID', 'user_DBID', 'ID', 'type', 'currency', 'amount', 'payout_tip', 'status', 'reject_cause'
                'payin_address', 'payin_amount', 'payout_src_address', 'payout_dst_address',
                'gw_error', 'gw_tx_id', 'gw_blockchane_id',
                'admin_action_at', 'gw_cb_at'
            ])
            async for row in txs:
                tx:Transaction = row[0]
                await writer.writerow([
                    tx.id, tx.user_id, tx.ext.ext, tx.tx_type_text, tx.currency, tx.amount, tx.payout_tip, tx.status_text, tx.reject_cause,
                    tx.payin_address, tx.payin_amount, tx.payout_src_address, tx.payout_dst_address,
                    tx.gw_error, tx.gw_tx_id, tx.gw_blockchane_id,
                    tx.admin_action_at_text, tx.gw_cb_at_text,
                ])
            logger.info(f'save users into temp file: {fname}')
            fs_file = FSInputFile(fname, filename=filename)
            return fs_file
    except IOError as ex:
        logger.error("can't create tx export file: %s", ex)
        if fname is not None:
            os.unlink(fname)
            return None

async def tx_export_cmd(msg: Message, state: FSMContext, dialog_manager: DialogManager, session: AsyncSession):
    await dialog_manager.reset_stack()
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=_('Для обработки'), callback_data='txexp:prc'),
            InlineKeyboardButton(text=_('Все'), callback_data='txexp:all')
        ]
    ])

    await msg.answer('Экспорт транзакция в CSV', reply_markup=keyboard)

@router.callback_query(F.data=='txexp:prc')
async def tx_exp_process(cbq: CallbackQuery, session: AsyncSession):
    if not cbq.message:
        return # TODO: show error
    await cbq.answer('Экспорт транзакций')
    filename = f'txs_{datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")}.csv'
    async with session.begin():
        tx_repo = TransactionRepo(session)
        txs = await tx_repo.get_for_processing_stream()
        fs_input = await tx_export(filename, txs)
    if fs_input:
        await cbq.message.answer_document(fs_input)
        os.unlink(fs_input.path)

@router.callback_query(F.data=='txexp:all')
async def tx_exp_all(cbq: CallbackQuery, state: FSMContext, session: AsyncSession):
    if not cbq.message:
        return
    await cbq.answer('Экспорт транзакций')
    await cbq.message.answer(_('Введите дату начала в формате ГГГГ-ММ-ДД'))
    await state.set_state(TxExportState.start_date)

async def parse_date_from_msg(msg: Message, err_text: str) -> str | None:
    if not msg.text:
        await msg.answer(err_text)
        return None
    date: datetime = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    date_str = msg.text.strip()
    if not date_str:
        await msg.answer(err_text)
        return None
    if date_str == YESTERDAY_TEXT:
        date-=timedelta(days=1)
    elif date_str == TODAY_TEXT:
        pass
    else:
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            await msg.answer(err_text)
            return None
    return date.astimezone(UTC).isoformat()

@router.message(TxExportState.start_date)
async def tx_exp_all_start_date(msg: Message, state: FSMContext):
    date = await parse_date_from_msg(msg, _('Введите дату начала в формате ГГГГ-ММ-ДД'))
    if not date:
        return
    await msg.answer(_(
        'Введите дату окончания в формате ГГГГ-ММ-ДД, дата окончания не включается в диапазон.'
    ))
    await state.update_data(start_date=date)
    await state.set_state(TxExportState.stop_date)

@router.message(TxExportState.stop_date)
async def tx_exp_all_stop_date(msg: Message, state: FSMContext, session: AsyncSession):
    date = await parse_date_from_msg(msg, _('Введите дату окончания в формате ГГГГ-ММ-ДД'))
    if not date:
        return
    data = await state.get_data()
    assert data and data['start_date']
    start_date = datetime.fromisoformat(data['start_date'])
    stop_date = datetime.fromisoformat(date)
    start_date_str = start_date.astimezone().strftime('%Y-%m-%d')
    stop_date_str = stop_date.astimezone().strftime('%Y-%m-%d')
    filename = f'txs_all_{start_date_str}-{stop_date_str}.csv'
    logger.info('start_date=%s, stop_date=%s', start_date, stop_date)
    async with session.begin():
        tx_repo = TransactionRepo(session)
        txs = await tx_repo.get_all_date_range_stream(start_date, stop_date, related=True)
        fs_input = await tx_export(filename, txs)
    if fs_input:
        await msg.answer_document(fs_input)
        os.unlink(fs_input.path)
    await state.clear()