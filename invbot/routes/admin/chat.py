import logging
from typing import Any
from aiogram import Router, Bot, F
from aiogram.types import ChatMemberUpdated, Message, BotCommandScopeChatAdministrators
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.utils.i18n import gettext as _
from aiogram_dialog import DialogManager
from ...db import AsyncSession
from ...db.models import Setting
from ...db.repo import SettingsRepo, AdminRepo, AdminInfo
from ...messages import messages
from ... import bot_admin_commands
import settings

logger = logging.getLogger(__name__)
router = Router(name=__name__)

@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER), F.chat.type=='group')
async def my_chat_member(cm: ChatMemberUpdated, session: AsyncSession, bot: Bot):
    logger.info(f'try to join group id={cm.chat.id}')
    is_success = True
    deleted: list[AdminInfo] = []
    inserted: list[AdminInfo] = []
    async with session.begin():
        setting_repo = SettingsRepo(session)
        admin_group = await setting_repo.get(Setting.Name.ADMIN_GROUP, for_update=True)
        if admin_group:
            logger.info(f'already joined to admins group id={admin_group.value}')
            if admin_group.value == cm.chat.id:
                logger.info('new group is current admin group, accept join')
            else:
                logger.info('leave umknown group')
                is_success = False
                await bot.leave_chat(cm.chat.id)    
        else:
            logger.info('admin group not set')
            if (settings.ADMINS_CHAT_ID is not None and settings.ADMINS_CHAT_ID != cm.chat.id):
                logger.info('leave group: ADMINS_CHAT_ID != group chat_id')
                is_success = False
                await bot.leave_chat(cm.chat.id)    
                return
            admin_group = Setting(name=Setting.Name.ADMIN_GROUP, value=cm.chat.id)
            await setting_repo.save(admin_group)
            logger.info(f'join admins groip: id={cm.chat.id}')
        if is_success:
            admin_repo = AdminRepo(session)
            chat_admins = await bot.get_chat_administrators(cm.chat.id)
            deleted, inserted = await admin_repo.sync_admins(chat_admins) #type: ignore
            logger.info('admin list synced')
        await bot.set_my_commands(bot_admin_commands, BotCommandScopeChatAdministrators(chat_id=cm.chat.id))
        logger.info('admin commands set')
        await cm.answer(messages.admins_list(deleted, inserted))

        # admin commands
        await cm.answer(messages.admin_help())
        
@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def chat_add_user(cm: ChatMemberUpdated):
    logger.info(cm)


@router.chat_member(ChatMemberUpdatedFilter(IS_MEMBER >> IS_NOT_MEMBER))
async def chat_remove_user(cm: ChatMemberUpdated):
    logger.debug(cm)

async def sync_cmd(msg: Message, settings: dict[str, Any], bot: Bot, session: AsyncSession, dialog_manager: DialogManager):
    await dialog_manager.reset_stack()
    if Setting.Name.ADMIN_GROUP not in settings:
        return
    chat_admins = await bot.get_chat_administrators(settings[Setting.Name.ADMIN_GROUP])
    async with session.begin():
        admin_repo = AdminRepo(session)
        deleted, inserted = await admin_repo.sync_admins(chat_admins) #type: ignore
    await msg.answer(messages.admins_list(deleted, inserted))
