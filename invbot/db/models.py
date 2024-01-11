from typing import Any
from datetime import datetime, UTC
from enum import StrEnum, IntEnum
import uuid

from sqlalchemy.engine.interfaces import Dialect
from aiogram.utils.i18n import gettext as _

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String, 
    BigInteger, 
    Boolean, 
    DateTime, 
    JSON, 
    types, 
    ForeignKey, 
    Float, 
    SmallInteger, 
    Text,
)
from . import engine
from ..tools import format_datetime, utc_now


class UTCDateTime(types.TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def process_result_value(self, value: Any | None, dialect: Dialect) -> datetime | None:
        if isinstance(value, str):
             return datetime.fromisoformat(value).replace(tzinfo=UTC)
        elif isinstance(value, datetime):
            return value.replace(tzinfo=UTC)

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> Any:
        if value is not None:
            return value.astimezone(UTC)
        return value            
        

class Base(DeclarativeBase):
    __as_dict__: list[str] = []

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, onupdate=utc_now)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in self.__as_dict__:
            result[key] = getattr(self, key)
        return result


class Account(Base):
    __tablename__ = 'account'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    users: Mapped[list['User']] = relationship(
        'User', back_populates='account', 
        passive_deletes=True, 
        passive_updates=True
    )


class User(Base):
    __tablename__ = 'user'

    __as_dict__ = [
        'id', 'phone_number', 'user_id', 'chat_id', 
        'bcast_status', 'bcast_status_text', 'last_visited', 'last_visited_text',
        'username', 'first_name', 'last_name', 'ag_message_id', 'account_id'
    ]

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(16), unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    bcast_status: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_visited: Mapped[datetime] = mapped_column(UTCDateTime)
    username: Mapped[str|None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str|None] = mapped_column(String(64), nullable=True)
    last_name: Mapped[str|None] = mapped_column(String(64), nullable=True)
    ag_message_id: Mapped[int|None] = mapped_column(BigInteger, nullable=True)
    exts: Mapped[list['Ext']] = relationship(
        back_populates='user', 
        cascade='all, delete-orphan',
        passive_deletes=True,
        passive_updates=True
    )
    transactions: Mapped[list['Transaction']] = relationship(
        back_populates='user', 
        cascade='all, delete-orphan',
        passive_deletes=True,
        passive_updates=True
    )
    account_id: Mapped[int|None] = mapped_column(
        ForeignKey('account.id', ondelete='SET NULL', onupdate='CASCADE'), 
        nullable=True
    )
    account: Mapped[Account] = relationship(Account, back_populates='users')
    
    @property
    def bcast_status_text(self):
        return _('Вкл') if self.bcast_status else _('Выкл')
        
    @property
    def last_visited_text(self) -> str:
        return format_datetime(self.last_visited)

    @property
    def created_at_text(self) -> str:
        return format_datetime(self.created_at)
    
    @property
    def account_name(self) -> str:
        return self.account.name if self.account else '-'


def get_path():
    return uuid.uuid4().hex

class Ext(Base):
    __tablename__  = 'ext'

    __as_dict__ = [
        'id', 'ext_id', 'user_id', 
    ]

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ext: Mapped[str] = mapped_column(String(128), unique=True)
    path: Mapped[str] = mapped_column(String(32), unique=True, default=get_path)
    user_id: Mapped[int] = mapped_column(ForeignKey('user.id'))
    user: Mapped[User] = relationship(back_populates='exts')
    transactions: Mapped[list['Transaction']] = relationship(
        'Transaction',
        back_populates='ext', 
        cascade='all, delete-orphan',
        passive_deletes=True,
        passive_updates=True
    )


class Transaction(Base):
    __tablename__ = 'transaction'

    class Status(IntEnum):
        NEW             = 0
        GW_ERROR        = 1 # notify client
        GW_PAYED        = 2 # payin: notify admin for acceptance
        GW_REJECTED     = 3 # notify client
        GW_SEND         = 4
        ADMIN_ACCEPTED  = 5 # notify client
        ADMIN_REJECTED  = 6

    class TxType(IntEnum):
        PAYIN          = 0
        PAYOUT         = 1
        SPECIAL_PAYIN  = 2
        SPECIAL_PAYOUT = 3

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user.id', ondelete='CASCADE', onupdate='CASCADE'))
    user: Mapped[User] = relationship(back_populates='transactions')
    ext_id: Mapped[int] = mapped_column(ForeignKey('ext.id', ondelete='CASCADE', onupdate='CASCADE'))
    ext: Mapped[Ext] = relationship(back_populates='transactions')
    tx_type: Mapped[int] = mapped_column(SmallInteger, default=TxType.PAYIN, index=True)
    currency: Mapped[str] = mapped_column(String(64))
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[Status] = mapped_column(SmallInteger, default=Status.NEW)

    payin_address: Mapped[str|None] = mapped_column(String(255), nullable=True)
    payin_amount: Mapped[float] = mapped_column(Float, nullable=True)

    payout_src_address: Mapped[str|None] = mapped_column(String(255), nullable=True)
    payout_dst_address: Mapped[str|None] = mapped_column(String(255), nullable=True)
    payout_tip: Mapped[float] = mapped_column(Float, default=0.0)

    gw_error: Mapped[str|None] = mapped_column(String(255), nullable=True)

    gw_tx_id: Mapped[int|None] = mapped_column(BigInteger, nullable=True)
    gw_blockchane_id: Mapped[str|None] = mapped_column(String(255), nullable=True)

    admin_action_at: Mapped[datetime|None] = mapped_column(UTCDateTime, nullable=True)
    gw_cb_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)

    gw_resp: Mapped[str|None] = mapped_column(Text, nullable=True)
    gw_cb: Mapped[str|None] = mapped_column(Text, nullable=True)

    reject_cause: Mapped[str|None] = mapped_column(String(255), nullable=True)

    @property
    def tx_type_text(self):
        if self.tx_type == Transaction.TxType.PAYIN or self.tx_type == Transaction.TxType.SPECIAL_PAYIN:
            return 'payin'
        return 'payout'
    
    @property
    def status_text(self):
        match self.status:
            case Transaction.Status.NEW: return _('К обработке')
            case Transaction.Status.GW_ERROR: return _('Ошибка отправки')
            case Transaction.Status.GW_PAYED: return _('Оплачена')
            case Transaction.Status.GW_REJECTED: return _('Отказ шлюза')
            case Transaction.Status.GW_SEND: return 'Отправлена на шлюз'
            case Transaction.Status.ADMIN_ACCEPTED: return _('Одобрена')
            case Transaction.Status.ADMIN_REJECTED: return _('Отклонена')
    
    @property
    def created_at_text(self):
        return format_datetime(self.created_at)
    
    @property
    def admin_action_at_text(self):
        return format_datetime(self.admin_action_at)
    
    @property
    def gw_cb_at_text(self):
        return format_datetime(self.gw_cb_at)

    @property
    def tx_type_sym(self):
        if self.tx_type == Transaction.TxType.PAYIN or self.tx_type == Transaction.TxType.SPECIAL_PAYIN:
            return '\u2192'
        return '\u2190'
    
    @property
    def can_accept(self) -> bool:
        return (
                self.tx_type == Transaction.TxType.PAYIN and self.status == Transaction.Status.GW_PAYED or 
                self.tx_type == Transaction.TxType.PAYOUT and self.status == Transaction.Status.NEW or
                self.tx_type == Transaction.TxType.SPECIAL_PAYIN and self.status == Transaction.Status.NEW or
                self.tx_type == Transaction.TxType.SPECIAL_PAYOUT and self.status == Transaction.Status.NEW
        )

    @property
    def can_deny(self) -> bool:
        return (
            self.tx_type == Transaction.TxType.PAYOUT and self.status == Transaction.Status.NEW or
            self.tx_type == Transaction.TxType.SPECIAL_PAYOUT and self.status == Transaction.Status.NEW or
            self.tx_type == Transaction.TxType.SPECIAL_PAYIN and self.status == Transaction.Status.NEW
        )
    
    @property
    def is_error(self) -> bool:
        return self.status in [Transaction.Status.GW_ERROR, Transaction.Status.GW_REJECTED]
    
class Admin(Base):
    __tablename__ = 'admin'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone_number: Mapped[str|None] = mapped_column(String(16), unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str|None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return ( 
            f'Admin(id={self.id}, '
            f'phone_number="{self.phone_number}", '
            f'user_id={self.user_id}, username="{self.username}")'
        )

class Setting(Base):
    __tablename__ = 'setting'

    class Name(StrEnum):
        ADMIN_GROUP = 'admin_group'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[Any] = mapped_column(JSON)


async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
