from aiogram import Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.utils.i18n import gettext as _
from ..db import AsyncSession
from ..db.models import User, Ext
from ..db.repo import ExtRepo

async def add_ext_ids(msg: Message, bot: Bot, state: FSMContext, user: User, session: AsyncSession):
    if not msg.text:
        await msg.answer(
            _(
                'Для работы бота нужен хотя бы один ID.\n'
                'Ведите все ваши ID через запятую, например:\n\n'
                'my_id1,my_id2,my_id_3'
            )
        )
        return False
    ext_ids = [ext_id.strip() for ext_id in msg.text.split(',')]
    user_extids = [Ext(user_id=user.id, ext=ext) for ext in ext_ids if ext]
    if not user_extids:
        await msg.answer(
            _(
                'Для работы бота нужен хотя бы один ID.\n'
                'Ведите все ваши ID через запятую, например:\n\n'
                'my_id1,my_id2,my_id_3'
            )
        ) 
        return False
    is_error = False
    async with session.begin():
        ext_repo = ExtRepo(session)
        if not await ext_repo.save_all(user_extids):
            is_error = True
    if is_error:
        await msg.answer(
            _(
                'Некоторые из указанных ID не могут быть добавлены.\n'
                'Проверте правильность написание ID'
            )
        )
        return False
    return True
