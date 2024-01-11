from aiogram.filters.callback_data import CallbackData
from enum import IntEnum, StrEnum


class CallbackID(StrEnum):
    pass

class UserRegData(CallbackData, prefix='ur'):
    user_id: int


class HelpData(CallbackData, prefix='uh'):
    chat_id: int
    message_id: int


class TransactionAction(IntEnum):
    ACCEPT  = 0
    DENY    = 1

class TransactionData(CallbackData, prefix='tx'):
    id: int
    action: TransactionAction