from typing import Any, Iterable
from enum import StrEnum
from aiogram import html
from aiogram.utils.i18n import gettext as _
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    User as TgUser
)
from .db.models import User, Transaction
from .db.repo import AdminInfo
from .callbacks import TransactionData, TransactionAction


class Messages:
    class Buttons(StrEnum):
        SEND_CONTACT = 'Отправить контакт',
        SET_CARD = 'Назначить карту'
        INPUT_PAYIN_ACC = 'Ввести'
        BACK = 'Назад'
        ACCEPT = 'Одобрить'
        DENY = 'Отклонить'

    @staticmethod
    def cant_process_reqest() -> str:
        return 'Запрос не может быть обработан в данный момент, попробуйте позже.'
    
    @staticmethod
    def bad_callback() -> str:
        return 'Запрос не может быть обработан, возможно сообщение устарело.'

    @staticmethod
    def common_error() -> str:
        return 'Произошла ошибка, попробуйте повторить операцию позже.'

    @staticmethod
    def user_info(user: User|dict[str, Any]) -> str:
        if isinstance(user, User):
            return (
                f'Ник: {html.quote(user.username or "")}, Тел.: {user.phone_number}\n'
                f'{html.quote(user.last_name or "")} {html.quote("user.first_name")}\n'
                f'Подключился: {user.created_at_text}\n'
            )
            
        return (
            f'Ник: {html.quote(user["username"])}, Тел.: {user["phone_number"]}\n'
            f'{html.quote(user["last_name"])} {html.quote(user["first_name"])}\n'
            f'Подключился: {user["created_at_text"]}\n'
        )

    @staticmethod
    def user_not_found() -> str:
        return 'Пользователь не найден, возможно сообщение устарело.'

    @staticmethod
    def user_have_account() -> str:
        return 'Аккаунт для пополнения уже установлен'

    @staticmethod
    def new_user_registered(user: User) -> str:
        return 'Зарегестрирован новый пользователь:\n' + Messages.user_info(user)

    @staticmethod
    def select_id() -> str:
        return 'Выберите ID'
    
    @staticmethod
    def select_currency() -> str:
        return 'Выберите валюту'

    @staticmethod
    def input_amount() -> str:
        return 'Введите сумму'

    @staticmethod
    def send_cache_receipt() -> str:
        return 'Отправить чек'

    @staticmethod
    def send_cache_receipt_photo() -> str:
        return 'Отправте фото чека'

    @staticmethod
    def send_account_screen() -> str:
        return 'Отправте скриншот аккаунта'

    @staticmethod
    def tx_info(tx: Transaction) -> str:
        text = (
            f'{tx.tx_type_sym}[{tx.id}] <b>{tx.tx_type_text}</b>\n'
            f'USER ID: {html.quote(tx.ext.ext)}\n'
            f'Сумма: {tx.amount} {tx.currency}'
        )
        if tx.tx_type == Transaction.TxType.PAYOUT or tx.tx_type == Transaction.TxType.SPECIAL_PAYOUT:
            text += f'\nЧаевые: {tx.payout_tip}'

        text += (
            f'\nСоздана: {tx.created_at_text}\n'
            f'Обработана: {tx.admin_action_at_text}'
        )

        if tx.tx_type == Transaction.TxType.SPECIAL_PAYIN:
            text += f'\nСчет: {html.quote(tx.user.account.name)}'
        elif tx.tx_type == Transaction.TxType.SPECIAL_PAYOUT:
            text += f'\nСчет: {html.quote(tx.payout_dst_address or "")}'
        
        text += f'\nСтатус: <b>{tx.status_text}</b>'
        
        if (
            tx.tx_type == Transaction.TxType.PAYIN and 
            tx.status in [Transaction.Status.GW_PAYED, Transaction.Status.ADMIN_ACCEPTED, Transaction.Status.ADMIN_REJECTED]
        ):
            text += f'\nОплаченная сумма: {tx.payin_amount or "-"}'
        if tx.tx_type == Transaction.TxType.PAYOUT:
            text += (
                f'\nАдрес отправителя:\n{html.quote(tx.payout_src_address or "")}\n'
                f'Aдрес получателя: {html.quote(tx.payout_dst_address or "")}\n'
            )
        if tx.gw_error:
            text += f'\nОшибка шлюза: {html.quote(tx.gw_error)}'
        return text

    @staticmethod
    def tx_base(tx: Transaction) -> str:
        return (
            f'{tx.tx_type_sym}[{tx.id}] <b>{tx.tx_type_text}</b>\n'
            f'Сумма: {tx.amount} {tx.currency}\n'
            f'Создана: {tx.created_at_text}\n'
            f'Статус: <b>{tx.status_text}</b>'
        )
    
    @staticmethod
    def tx_not_found():
        return 'Транзакция не найдена'
    
    @staticmethod 
    def tx_payed(tx: Transaction, full: bool = True) -> str:
        return '<b>Транзакция оплачена.</b>\n' + (Messages.tx_info(tx) if full else Messages.tx_base(tx))

    @staticmethod 
    def tx_accepted(tx: Transaction, full: bool=True) -> str:
        return '<b>Транзакция одобрена.</b>\n' + (Messages.tx_info(tx) if full else Messages.tx_base(tx))

    @staticmethod
    def tx_rejected(tx: Transaction, full: bool = True) -> str:
        text = '<b>Транзакция отклонена.</b>\n' + (Messages.tx_info(tx) if full else Messages.tx_base(tx))
        if tx.reject_cause is not None:
            text += f'\nПричина отказа: {html.quote(tx.reject_cause)}'
        return text
    
    @staticmethod
    def tx_rejected_short() -> str:
        return "Транзакция отклонена"

    @staticmethod
    def tx_error(tx: Transaction, full: bool = True) -> str:
        return (
            f'<b>Транзакция завершилась ошибкой.</b>\n'
            f'{Messages.tx_info(tx) if full else Messages.tx_base(tx)}\n'
        )
    
    @staticmethod
    def tx_error_cb() -> str:
        return 'Транзакция завершилась ошибкой.'

    @staticmethod
    def crypto_gw_error(gw_error: str | None = None) -> str:
        if gw_error is not None:
            return f'Ошибка шлюза криптоплатежей: {html.quote(gw_error)}'
        else:
            return 'Ошибка шлюза криптоплатежей.'

    @staticmethod
    def http_error() -> str:
        return 'Ошибка при отправке запроса на шлюз криптоплатежей.'
    
    @staticmethod
    def exception(ex: Exception) -> str:
        return 'Произошла ошибка, передайте администратору следующие данные:\n {ex}'.format(ex=html.quote(str(ex)))

    @staticmethod
    def amount_error() -> str:
        return 'Неправильная сумма, введите сумму еще раз'
    
    @staticmethod
    def new_transaction(tx: Transaction) -> tuple[str, InlineKeyboardMarkup]:
        text =  f'Новая транзакция\n {Messages.tx_info(tx)}'
        buttons = [
            InlineKeyboardButton(
                text=Messages.Buttons.ACCEPT, 
                callback_data=TransactionData(id=tx.id, action=TransactionAction.ACCEPT).pack()
            ), 
        ]
        if tx.can_deny:
            buttons.append(
                InlineKeyboardButton(
                    text=Messages.Buttons.DENY, 
                    callback_data=TransactionData(id=tx.id, action=TransactionAction.DENY).pack()
                ), 
            )
        return text, InlineKeyboardMarkup(inline_keyboard=[buttons])
    
    @staticmethod
    def payin(amount: float, currency: str, address: str) -> str:
        return (
            f'Переведите <b>{amount} {currency}</b> на указанный адрес.\n'
            'После получения средств транзакция будет проверена и одобрена, '
            'после этого сумма будет зачислена на баланс.\n\n'
            'Адрес:\n'
            f'<code>{html.quote(address)}</code>'
        )
    
    @staticmethod
    def payin_special(tx: Transaction) -> str:
        return (
            f'Переведите <b>{tx.amount} {tx.currency}</b> на указанный cчет.\n'
            'После получения средств транзакция будет проверена и одобрена, '
            'после этого сумма будет зачислена на баланс.\n\n'
            'Счет:\n'
            f'<code>{html.quote(tx.user.account.name)}</code>'
        )
    
    @staticmethod 
    def payin_sent(tx: Transaction) -> str:
        return (
            f'{Messages.tx_base(tx)}\n'
            'Ваша транзакция отправлена администраторам и ожидает одобрения.\n'
            'Вы получите уведомление о статусе транзакции.'
        )

    @staticmethod
    def payout(tx: Transaction) -> str:
        return (
            f'{Messages.tx_base(tx)}\n'
            'Ваша транзакция отправлена администраторам и ожидает одобрения.\n'
            'Вы получите уведомление о статусе транзакции.'
        )

    @staticmethod
    def payout_special(tx: Transaction) -> str:
        return (
            f'[{tx.id}]\n'
            f'Ожидайте пополнения указанного счета - {html.quote(tx.payout_dst_address or "")}. '
            'После пополнеия Вам придет уведомление.'
        )

    @staticmethod
    def payout_tip(value: bool) -> str:
        if value:
            return 'Оставить чаевые: Да'
        return 'Оставить чаевые: Нет'

    @staticmethod
    def payout_select_currency() -> str:
        return (
            'Выбирите валюту для вывода:\n'
            'Если хотите оставить чаевые кассиру, то кликните по кнопке <b>Оставить чаевые</b>.'
        )

    @staticmethod
    def no_pay() -> str:
        return 'В данный момент оплата невозможна'

    @staticmethod
    def contact_data(tg_user: TgUser | None) -> str:
        if tg_user:
            text = (
                f'Здравствуйте, {html.quote(tg_user.username or "")}. '
                'Для продолжения нам нужны Ваши контактные даные, чтобы предоставить их, '
                'кликните по кнопке <b>"Отправить контакт"</b>'
            )
        else:
            text = (
                f'Здравствуйте.'
                'Для продолжения нам нужны Ваши контактные даные, чтобы предоставить их, '
                'кликните по кнопке <b>"Отправить контакт"</b>'
            )
        return text
    
    @staticmethod
    def already_registered():
        return (
            'Спасибо! Вы уже подключены к сервису.\n'
            'Мы обновили Ваши контактные данные.'
        )

    @staticmethod
    def input_id_request() -> str:
        return (
            'Ведите все ваши ID через запятую'
        )

    @staticmethod
    def thank_you_register() -> str:
        return (
            'Спасибо за регистрацию. Теперь Вы можете пополнять счета и выводить средства.\n'
            '/payin - пополнение счета\n'
            '/payout - выведение средств'
        )
    
    @staticmethod
    def check_input() -> str:
        return 'Проверте правильность ввода.'
    
    @staticmethod
    def account_exists() -> str:
        return 'Счет уже существует'
    
    @staticmethod
    def input_payin_account() -> str:
        return 'Введите аккаунт для пополнения счета, ответив на это сообщение'
    
    @staticmethod
    def select_payin_account() -> str:
        return 'Выберите аккаунт для пополнения счета'

    @staticmethod
    def payin_account_ok() -> str:
        return 'Аккаунт для пополнения счета установлен'

    @staticmethod
    def wallet_input() -> str:
        return 'Введите адрес кошелька, на который хотите получить средства'

    @staticmethod
    def account_input() -> str:
        return 'Введите cчет, на который хотите получить средства'
    
    @staticmethod
    def tx_cant_accepted() -> str:
        return 'Данную транзакцию нельзя одобрить.'
    
    @staticmethod
    def tx_cant_deny() -> str:
        return 'Данную транзакцию нельзя отклонить.'
    
    @staticmethod
    def input_message() -> str:
        return 'Введите сообщение, отправив ответ на это сообщение'
    
    @staticmethod
    def search_id_phone() -> str:
        return 'Введите ID или номер телефона, отправив ответ на это сообщение'
    
    @staticmethod
    def admins_list(deleted:Iterable[AdminInfo], inserted: Iterable[AdminInfo]) -> str:
        text = 'Удаленные администраторы:\n'
        text += '\n'.join([f'- {a.user_id} - {html.quote(a.username or "")}' for a in deleted])
        text += '\n' + 'Добавленные администраторы:\n'
        text += '\n'.join([f'+ {a.user_id} - {html.quote(a.username or "")}' for a in inserted])
        return text

    @staticmethod
    def jackpot() -> str:
        return 'Для уточнения информации свяжитесь с  <a href="https://t.me/kassa_bombay">Bombay</a>'

    @staticmethod
    def admin_help():
        return (
            '<b>Команды администратора</b>\n'
            '/id - поиск пользователя по ID или номеру телефона\n'
            '/regs - новые регистрации\n'
            '/txl - список транзакций\n'
            '/txexp - экспорт транзакций в excel (csv)\n'
            '/userexp - экспорт пользователей в excel (csv)\n'
            '/admsync - синхронизировать список администраторов с группой\n'
            '/help - помощь (данное сообщение)'
        )

    @staticmethod
    def help():
        return (
            '<b>Доступные комманды:</b>\n'
            '/start - подключение к боту\n'
            '/registration - как зарегестрироваться в приложении\n'
            '/payin - пополнить баланс.\n'
            '/payout - вывести средства.\n'
            '/ask - связаться с кассой\n'
            '/settings - информация об аккаунте и настройки.\n'
            '/jackpot - информация о джекпоте\n'
            '/help - помощь (данное сообщение).'
        )

    @staticmethod
    def start_help():
        return (
            '<b>Для регистрации в приложении необходимо:</b>\n'
            'а) в строку ID клуба введите 708 708\n'
            'б) в строку ID агента введите ID вашего агента (обязательно)\n'
            'в) в случае если у вас нет агента, перейдите в «связаться с кассой» для получения действующего ID.\n'
            'г) вступить.'
        )

    @staticmethod
    def ask_question() -> str:
        return 'Связаться с кассой'

    @staticmethod
    def unknown_msg_help() -> str:
        return (
            'Вы ввели текстовое сообщение, чтобы продолжать общаться с Bombaybo, введите одну из команд:\n' + Messages.help()
        )
    
    @staticmethod
    def tx_deny_select_cause() -> str:
        return "Укажите причину отказа"
    
    @staticmethod
    def tx_deny_input_custom() -> str:
        return "Введите свою причину отказа, ответив на это сообщение"

    @staticmethod
    def tx_deny_causes() -> list[tuple[int, str]]:
        return [
            (1, "Неверные реквизиты"),
            (2, "Недостаточно средств"),
            (100, "Причина не указана"),
            (0, "Ввести свою причину")
        ]
    
messages = Messages
