import logging
from typing import Any, cast
from enum import StrEnum, IntEnum
from pprint import pformat
from json.decoder import JSONDecodeError
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.utils.i18n.core import I18n
import aiohttp
from aiohttp import web
import settings
from ..db import SessionMaker
from ..db.models import Transaction, Setting
from ..db.repo import TransactionRepo, SettingsRepo, ExtRepo
from ..tools import utc_now
from ..messages import messages

logger = logging.getLogger(__name__)

class Status(StrEnum):
    SUCCESS = 'Success'

class BithideTxType(IntEnum):
    Deposit    = 1
    Withdrawal = 2

# {
#  'AdditionalInfo': '8',
#  'Address': 'tb1qkawfz0qevnutx9lmh7l7gtqua07et75h70hz65',
#  'Amount': 1e-08,
#  'Comment': '',
#  'Currency': 'BTC',
#  'Date': '2023-10-28T11:15:15.3410953Z',
#  'Error': None,
#  'ExternalId': '8',
#  'Id': 441,
#  'Initiator': 'ExternalDeposit',
#  'RequestId': None,
#  'TxId': 'd056e1a9bad4d281b58af4216de4c0dd2670e1e58016556103a42120023fb184',
#  'Type': 1
# }
async def callback(request: web.Request):
    if settings.BITHIDE_SERVER_IP and request.remote not in settings.BITHIDE_SERVER_IP:
        logger.error('bithide server ip rejected: %s', request.remote)
        raise web.HTTPNotFound()
    
    try:
        data: Any = await request.json()
    except (ValueError, JSONDecodeError, aiohttp.ContentTypeError) as ex:
        logger.error('body parse error: %s', ex)
        raise web.HTTPBadRequest()
    
    if not isinstance(data, dict):
        logger.error('body must be json object')
        raise web.HTTPBadRequest()

    data = cast(dict[str, Any], data)

    try:
        bithide_external_id = str(data['ExternalId'])
    except (ValueError, TypeError, KeyError):
        logger.error('ExternalID not found')
        raise web.HTTPBadRequest()

    try:
        bithide_tx_type = int(data['Type'])
    except (ValueError, TypeError, KeyError):
        logger.error('bad bithide_tx_type')
        raise web.HTTPBadRequest()

    try:
        bithide_amount = float(data['Amount'])
    except (ValueError, TypeError, KeyError):
        logger.error('bad amount')
        raise web.HTTPBadRequest()

    tx_id: int | None = None
    try:    
        tx_id = int(data['RequestId'])
    except (ValueError, TypeError, KeyError):
        pass

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug('data=%s', pformat(data))
    
    cb_error: str | dict[str, Any] | None = data.get('Error')
    if isinstance(cb_error, dict):
        cb_error = cb_error.get('Code')
    
    currency = data.get('Currency')
    logger.info('bihide callback: error=%s, currency=%s, tx_id=%s, amount=%s, external_id=%s', 
                cb_error, 
                currency, 
                tx_id, 
                bithide_amount,
                bithide_external_id
                )
    session_maker: SessionMaker = request.app['session_maker']
    bot:Bot = request.app['bot']
    assert isinstance(bot, Bot)

    admin_group_id: int | None = None
    async with session_maker() as session:
        async with session.begin():
            setting_repo = SettingsRepo(session)
            admin_group_id = await setting_repo.get_value(Setting.Name.ADMIN_GROUP)

            # try to get ext
            ext_repo = ExtRepo(session)
            ext = await ext_repo.get_by_ext(bithide_external_id, related=True)
            if not ext:
                logger.error('ext not found: %s', bithide_external_id)
                raise web.HTTPBadRequest()
            # try to get user

            tx_repo = TransactionRepo(session)
            if bithide_tx_type == BithideTxType.Deposit:
                tx = Transaction(
                    tx_type=Transaction.TxType.PAYIN,
                    currency=currency or 'USDT-TRC20', 
                    amount=bithide_amount, 
                    payin_amount=bithide_amount,
                    user_id=ext.user.id, 
                    ext_id=ext.id, 
                    status=Transaction.Status.NEW
                )
                session.add(tx)
                await session.flush()
                tx = await tx_repo.get_by_id(tx.id, related=True)
            elif bithide_tx_type == BithideTxType.Withdrawal and tx_id:
                tx = await tx_repo.get_by_id(tx_id, related=True, for_update=True)
                if not tx:
                    raise web.HTTPBadRequest(text='tx not found')
            else:
                logger.error('unknown bithide_tx_type or tx_id is None: %d, %s', bithide_tx_type, tx_id)
                raise web.HTTPBadRequest()
            assert tx
            tx.gw_cb_at = utc_now()
            
            if cb_error:
                tx.status = Transaction.Status.GW_REJECTED
                tx.gw_error = str(cb_error)
            else:
                tx.status = Transaction.Status.GW_PAYED
                tx.gw_tx_id = data.get('Id')
                tx.gw_blockchane_id = data.get('TxId')
                if tx.tx_type == Transaction.TxType.PAYIN:
                    try:
                        tx.payin_amount = float(data.get('Amount'))
                    except (ValueError, TypeError):
                        pass

    i18n:I18n = request.app['i18n']
    with i18n.context(), i18n.use_locale('ru'):
        try:
            if tx.is_error:
                await bot.send_message(tx.user.chat_id, messages.tx_error(tx, full=False))
            else:
                await bot.send_message(tx.user.chat_id, messages.tx_payed(tx, full=False))
            # admin notify
            if admin_group_id:
                if tx.tx_type == Transaction.TxType.PAYOUT:
                    if tx.is_error:
                        await bot.send_message(admin_group_id, messages.tx_error(tx))
                    else:
                        await bot.send_message(admin_group_id, messages.tx_payed(tx))
                elif tx.tx_type == Transaction.TxType.PAYIN:
                    text, reply_markup = messages.new_transaction(tx)
                    await bot.send_message(admin_group_id, text, reply_markup=reply_markup)
            else:
                logger.warn('andmin group not set, no messages send on payout to admin group')
        except TelegramAPIError as ex:
            logger.exception(ex)
    return web.Response(text="OK")

# "ExternalId": "1",
# "Currency": "BTC",
# "New": true,
# "ExpectedAmount": 0.0000001,
# "PublicKey": "z13ovzyQ0yu/EfaTKXHc1Q=="
async def _api_post(url: str, data: dict[str, Any], session: aiohttp.ClientSession) -> tuple[int, dict[str, Any] | None]:
    async with session.post(
        f'{settings.BITHIDE_URL}{url}',
        json=data
    ) as resp:
        result: dict[str, Any] | None = None
        try:
            result = await resp.json(content_type=None)
        except (aiohttp.ContentTypeError, JSONDecodeError, ValueError):
            pass            
        logger.info('status=%d, data=%s', resp.status, pformat(result))
        return resp.status, result

async def get_address(session: aiohttp.ClientSession, ext: str, currency: str, amount: float) -> tuple[int, dict[str, Any] | None]:
    data = {
            "ExternalId": ext, #str(tx.id),
            "Currency": currency,
            "New": False,
            "ExpectedAmount": amount,
            "AdditionalInfo": '',
            "CallbackLink": f'{settings.BITHIDE_CALLBACK_URL}',
            "PublicKey": settings.BIHIDE_PUBLIC_KEY
        }
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug('get_address: data=%s', pformat(data))
    else:
        logger.info('get_address: ext=%s, currency=%s, amount=%f', ext, currency, amount)
    return await _api_post('/Address/GetAddress', data, session)
    
async def withdraw(session: aiohttp.ClientSession, tx: Transaction) -> tuple[int, dict[str, Any] | None]:
    data = {
            "RequestId": str(tx.id),
            "Currency": tx.currency,
            "Amount": tx.amount,
            "SourceAddress": tx.payout_src_address,
            'DestinationAddress': tx.payout_dst_address,
            "AdditionalInfo": tx.ext.ext,
            "CallbackLink": f'{settings.BITHIDE_CALLBACK_URL}',
            "IsSenderCommision": True,
            "Comment": f'payout: {tx.ext.ext}',
            "PublicKey": settings.BIHIDE_PUBLIC_KEY
        }
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug('withdrawal data=%s', pformat(data))
    else:
        logger.debug('withdrawal: tx_id=%d, currency=%s, amount=%f', tx.id, tx.currency, tx.amount)
    return await _api_post('/Transaction/Withdraw', data, session)