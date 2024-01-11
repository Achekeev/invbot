from datetime import UTC, datetime
from aiogram.types import Update, Chat, User as TgUser
import settings

def format_datetime(dt: datetime|None) -> str:
    if dt is None:
        return '-'
    return dt.astimezone().strftime(settings.DATETIME_FORMAT)

def get_user_chat(update: Update):
    user: TgUser | None = None
    chat: Chat | None = None
    if update.message:
        chat = update.message.chat
        user = update.message.from_user
    elif update.edited_message:
        chat = update.edited_message.chat
        user = update.edited_message.from_user
    elif update.channel_post:
        chat = update.channel_post.chat
        user = update.channel_post.from_user
    elif update.edited_channel_post:
        chat = update.edited_channel_post.chat
        user = update.edited_channel_post.from_user
    elif update.inline_query:
        user = update.inline_query.from_user
    elif update.chosen_inline_result:
        user = update.chosen_inline_result.from_user
    elif update.callback_query:
        if update.callback_query.message:
            chat = update.callback_query.message.chat
        user = update.callback_query.from_user
    elif update.shipping_query:
        user = update.shipping_query.from_user
    elif update.pre_checkout_query:
        user = update.pre_checkout_query.from_user
    elif update.poll_answer:
        user = update.poll_answer.user
        chat = update.poll_answer.voter_chat
    elif update.my_chat_member:
        chat = update.my_chat_member.chat
        user = update.my_chat_member.from_user
    elif update.chat_member:
        chat = update.chat_member.chat
        user = update.chat_member.from_user
    elif update.chat_join_request:
        chat = update.chat_join_request.chat
        user = update.chat_join_request.from_user

    return user, chat


def utc_now():
    return datetime.now(tz=UTC)


def normalize_phone(phone_number: str) -> str:
    if len(phone_number) <= 0:
        return phone_number
    if phone_number[0] != '+':
        return f'+{phone_number}'
    return phone_number