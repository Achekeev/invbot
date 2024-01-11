import logging
from typing import Any
from datetime import datetime
from collections.abc import Iterable
from dataclasses import dataclass
from sqlalchemy import select, update, delete, insert, or_, and_
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from aiogram.types import ChatMemberAdministrator
from .models import Setting, User, Admin, Ext, Transaction, Account

logger = logging.getLogger(__name__)

class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class AccountRepo(Repository):
    async def get_all(self, limit: int = 100):
        if limit <= 0:
            limit = 100
        stmt = select(Account).order_by(Account.id.desc())
        return await self.session.scalars(stmt)
    
    async def get_by_id(self, id: int) -> Account | None:
        stmt = select(Account).where(Account.id==id)
        return await self.session.scalar(stmt)
    
    async def get_by_name(self, name: str) -> Account | None:
        stmt = select(Account).where(Account.name==name)
        return await self.session.scalar(stmt)


class UserRepo(Repository):
    async def get_by_user_id(self, user_id: int, for_update: bool = False) -> User|None:
        stmt = select(User).where(User.user_id == user_id) 
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def get_by_id(self, id: int, for_update: bool = False, related: bool = False) -> User|None:
        stmt = select(User).where(User.id == id) 
        if for_update:
            stmt = stmt.with_for_update()
        if related:
            stmt = stmt.options(joinedload(User.account))
        return await self.session.scalar(stmt)
    
    async def get_by_ext(self, ext: str, for_update: bool = False, related: bool = False) -> User|None:
        stmt = select(User).where(User.exts.any(Ext.ext==ext)) 
        if for_update:
            stmt = stmt.with_for_update()
        if related:
            stmt = stmt.options(joinedload(User.account))
        return await self.session.scalar(stmt)

    async def get_by_phone_number(self, phone_number: str, for_update: bool = False, related: bool = False) -> User|None:
        stmt = select(User).where(User.phone_number == phone_number) 
        if for_update:
            stmt = stmt.with_for_update()
        if related:
            stmt = stmt.options(joinedload(User.account))
        return await self.session.scalar(stmt)
    
    async def get_without_account(self, limit: int = 100):
        if limit <= 0:
            limit = 100
        stmt = select(User).where(User.account_id.is_(None)).order_by(User.id.desc())
        return await self.session.scalars(stmt)

    async def set_bcast_status(self, user_id: int, status: bool):
        stmt = update(User).where(User.id==user_id).values(bcast_status=status)
        return self.session.execute(stmt)

    async def update(self, user_id: int, **kwargs: Any):
        stmt = update(User).where(User.id==user_id).values(**kwargs)
        await self.session.execute(stmt)
        return
            
    async def get_bcast(self): 
        stmt = select(User).where(User.bcast_status==True)
        result = await self.session.stream(stmt)
        return result
    
    async def get_all_stream(self, with_exts:bool=False):
        stmt = select(User)
        if with_exts:
            stmt = stmt.options(joinedload(User.exts))
        return await self.session.stream(stmt)
    
    async def set_account_by_id(self, id: int, account_id: int):
        stmt = update(User).where(User.id==id).values(account_id=account_id)
        return await self.session.execute(stmt)

    async def save(self, user: User):
        self.session.add(user)


class ExtRepo(Repository):
    async def save(self, user: User):
        self.session.add(user)

    async def get_by_ext(self, ext: str, related: bool = False):
        stmt = select(Ext).where(Ext.ext==ext)
        if related:
            stmt = stmt.options(joinedload(Ext.user))
        return await self.session.scalar(stmt)
    
    async def get_by_id(self, id: int, related: bool = False, for_update: bool = False) -> Ext | None:
        stmt = select(Ext).where(Ext.id==id)
        if related:
            stmt = stmt.options(joinedload(Ext.user))
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def get_latest(self, user_id: int, limit:int=100):
        if limit <= 0:
            limit = 100
        stmt = select(Ext).where(Ext.user_id==user_id).order_by(Ext.id.desc()).limit(limit)
        return await self.session.scalars(stmt)

    async def save_all(self, ext_ids: Iterable[Ext]):
        self.session.add_all(ext_ids)
        try:
            await self.session.flush()
        except IntegrityError:
            return False
        return True


class TransactionRepo(Repository):
    async def get_by_id(self, id: int, related:bool=False, for_update: bool = False):
        stmt = select(Transaction).where(Transaction.id==id)
        if related:
            stmt = stmt.options(joinedload(Transaction.user).joinedload(User.account), joinedload(Transaction.ext))
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def get_for_callback(self, amount: float, ext_id: int, related: bool = True, for_update: bool = False):
        stmt = select(Transaction).where(
            Transaction.tx_type==Transaction.TxType.PAYIN,
            Transaction.status==Transaction.Status.GW_SEND,
            Transaction.amount==amount,
            Transaction.ext_id==ext_id
        ).order_by(Transaction.id.desc()).limit(1)
        if related:
            stmt = stmt.options(joinedload(Transaction.user).joinedload(User.account), joinedload(Transaction.ext))
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def get_all(
            self, tx_type: Transaction.TxType | None = None, 
            status: Transaction.Status  | Iterable[Transaction.Status] | None = None, 
            user_id: int|None = None, 
            reverse: bool = True,
            limit:int=100
        ):
        stmt = select(Transaction)
        if tx_type is not None:
            stmt = stmt.where(Transaction.tx_type==tx_type)
        if status is not None:
            if isinstance(status, Iterable):
                stmt = stmt.where(Transaction.status.in_(status))
            else:
                stmt = stmt.where(Transaction.status==status)
        if user_id is not None:
            stmt = stmt.where(Transaction.user_id==user_id)
        if reverse:
            stmt = stmt.order_by(Transaction.id.desc())
        if limit <= 0:
            limit = 100
        stmt = stmt.limit(limit).options(joinedload(Transaction.ext), joinedload(Transaction.user))
        return await self.session.scalars(stmt)

    def _stmt_processed(self):
        stmt = select(Transaction).where(
            or_(
                and_(
                    Transaction.tx_type==Transaction.TxType.PAYIN,
                    Transaction.status==Transaction.Status.GW_PAYED
                ),
                and_(
                    Transaction.tx_type==Transaction.TxType.SPECIAL_PAYIN,
                    Transaction.status==Transaction.Status.NEW
                ),
                and_(
                    Transaction.tx_type==Transaction.TxType.PAYOUT,
                    Transaction.status==Transaction.Status.NEW
                ),
                and_(
                    Transaction.tx_type==Transaction.TxType.SPECIAL_PAYOUT,
                    Transaction.status==Transaction.Status.NEW
                )
            )
        )
        return stmt

    async def get_for_processing(self, user_id: int | None = None, limit:int=100):
        if limit <= 0:
            limit = 100
        stmt = self._stmt_processed().limit(limit).options(
            joinedload(Transaction.user).joinedload(User.account), 
            joinedload(Transaction.ext)
        )
        if user_id is not None:
            stmt = stmt.where(Transaction.user_id==user_id)
        return await self.session.scalars(stmt)

    async def get_for_processing_stream(self):
        stmt = self._stmt_processed()
        return await self.session.stream(stmt)

    async def admin_accept(self, id:int):
        stmt = update(Transaction).where(Transaction.id==id).values(status=Transaction.Status.ADMIN_ACCEPTED)
        await self.session.execute(stmt)

    async def admin_deny(self, id:int):
        stmt = update(Transaction).where(Transaction.id==id).values(status=Transaction.Status.ADMIN_REJECTED)
        await self.session.execute(stmt)

    async def get_all_date_range_stream(
            self, start_date: datetime | None = None, 
            stop_date: datetime | None = None,
            related: bool = False
        ):
        stmt = select(Transaction)
        if start_date is not None:
            stmt = stmt.where(Transaction.created_at>=start_date)
        if stop_date is not None:
            stmt = stmt.where(Transaction.created_at<stop_date)
        if related:
            stmt = stmt.options(joinedload(Transaction.ext), joinedload(Transaction.user))
        return await self.session.stream(stmt)


@dataclass
class AdminInfo():
    user_id: int
    username: str|None

class AdminRepo(Repository):
    async def get_all(self):
        stmt = select(Admin)
        admins = await self.session.scalars(stmt)
        return admins
    
    async def sync_admins(self, chat_admins: list[ChatMemberAdministrator]) -> tuple[list[AdminInfo], list[AdminInfo]]:
        db_admins = list(await self.get_all())
        db_admins_ids = set([a.user_id for a in db_admins])
        chat_admins_ids = set([ca.user.id for ca in chat_admins])

        ids_for_delete = db_admins_ids - chat_admins_ids
        ids_for_insert = chat_admins_ids - db_admins_ids

        # delete old admins
        if ids_for_delete:
            stmt = delete(Admin).where(Admin.user_id.in_(ids_for_delete))
            await self.session.execute(stmt)

        #insert new admins
        admins_for_insert = [
            {'user_id': ca.user.id, 'username': ca.user.username} 
            for ca in chat_admins if ca.user.id in ids_for_insert
        ]
        if admins_for_insert:
            await self.session.execute(insert(Admin), admins_for_insert)

        deleted = [
            AdminInfo(user_id=a.user_id, username=a.username)
            for a in db_admins if a.user_id in ids_for_delete
        ]

        inserted = [
            AdminInfo(user_id=ca.user.id, username=ca.user.username)
            for ca in chat_admins if ca.user.id in ids_for_insert
        ]

        return deleted, inserted

class SettingsRepo(Repository):
    async def get(self, name: str, for_update:bool=False) -> Setting|None:
        stmt = select(Setting).where(Setting.name==name)
        if for_update:
            stmt = stmt.with_for_update()
        value = await self.session.scalar(stmt)
        return value
    
    async def get_value(self, name: str) -> Any:
        stmt = select(Setting.value).where(Setting.name==name)
        value = await self.session.scalar(stmt)
        return value

    async def get_all(self, names: Iterable[str]|None = None) -> dict[str, Any]:
        if names is None:
            stmt = select(Setting)
        else:
            stmt = select(Setting).where(Setting.name.in_(names))
        settings = await self.session.scalars(stmt)
        result: dict[str, Any] = {}
        for s in settings:
            result[s.name] = s.value
        return result

    async def set_value(self, name:str, value:Any):
        setting = await self.get(name, for_update=True)
        if setting:
            setting.value = value
        else:
            setting = Setting(name=name, value=value)
        await self.save(setting)

    async def save(self, setting: Setting):
        self.session.add(setting)


