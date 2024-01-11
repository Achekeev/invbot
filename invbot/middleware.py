import logging
from collections.abc import Callable, Awaitable
from typing import  Any, Dict, cast
from pprint import pformat
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from .db.repo import SettingsRepo, UserRepo, AdminRepo
from .db.models import User, Admin
from .db import SessionMaker, AsyncSession
from . import tools
from pprint import pformat

logger = logging.getLogger(__name__)

class DBSessionMeddleware(BaseMiddleware):
    def __init__(self, maker: SessionMaker) -> None:
        self.session_maker = maker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with self.session_maker() as session:
            data['session'] = session
            return await handler(event, data)
        

class PreloadDataMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        session: AsyncSession = data['session']
        update = cast(Update, event)
        tg_user, chat = tools.get_user_chat(update)
        data['chat'] = chat
        data['tg_user'] = tg_user
        data['user'] = None
        data['settings'] = {}
        user: User | None = None
        async with session.begin():
            user_repo = UserRepo(session)
            setting_repo = SettingsRepo(session)
            admin_repo = AdminRepo(session)
            if tg_user:
                user = await user_repo.get_by_user_id(tg_user.id)
            # update last_visited
            if user:
                user.last_visited = tools.utc_now()
            data['user'] = user
            data['settings'] = await setting_repo.get_all()
            # load admins
            admins = await admin_repo.get_all()
            data['admins'] = list(admins)
            # check is user admin
            admin: Admin | None = None
            if tg_user:
                admin = next((x for x in data['admins'] if x.user_id == tg_user.id), None)
            data['is_admin'] = admin is not None
        
        logger.info('data loaded')
        logger.debug('set data:\n*** chat=%s\n*** tg_user=%s\n*** user=%s\n*** settings=%s\n*** admins=%s',
                     pformat(chat), 
                     pformat(tg_user), 
                     pformat(user), 
                     pformat(data['settings']), 
                     pformat(data['admins'])
        )
        return await handler(event, data)
