import logging
from typing import Any
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery, Update, User as TgUser, Chat
from magic_filter import MagicFilter
from .db.models import Setting, User, Admin

logger = logging.getLogger(__name__)

class AdminFilter(Filter):
    async def __call__(self, 
                       update: Message | CallbackQuery, 
                       settings: dict[str, Any], 
                       admins: list[Admin],
                       chat: Chat,
                       tg_user: TgUser
                       ) -> Any:                        
        if chat and chat.id == settings.get(Setting.Name.ADMIN_GROUP):
            logger.info('admin access granted for admin group: %d', chat.id)
            return True # chat is admins group
        
        # if tg_user and tg_user.id and tg_user.id in [a.user_id for a in admins]:
        #     logger.info('admin access granted for user: %d', tg_user.id)
        #     return True
        logger.info('admin access denied: %d', tg_user.id)
        return False

# User filter
class UserFilter(Filter):
    def __init__(self, magic_filter: MagicFilter | None = None) -> None:
        self.magic_filter = magic_filter

    async def __call__(self, update: Update | Message | CallbackQuery, user: User|None) -> Any:
        if user and (not self.magic_filter or self.magic_filter.resolve(user)):
            logger.info('user access granted for: id=%d', user.id)
            return True
        return False
