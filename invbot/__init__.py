from aiogram.types import BotCommand
   
bot_commands = [
    BotCommand(command='/help', description='Помощь и вопросы администратору'),
    BotCommand(command='/registration', description='как зарегестрироваться в приложении'),
    BotCommand(command='/settings', description='Информаци об аккаунте и настройки'),
    BotCommand(command='/payin', description='Пополнение счета'),
    BotCommand(command='/payout', description='Выведение средств'),
    BotCommand(command='/ask', description='Связаться с кассой'),
    BotCommand(command='/jackpot', description='Информация о джекпоте')
]

bot_admin_commands = [
    BotCommand(command='/help', description='Помощь'),
    BotCommand(command='/txl', description='Список транзакций'),
    BotCommand(command='/regs', description='Список пользователей, ожидающих регистрации'),
    BotCommand(command='/id', description='Информация о пользователе по ID или номеру телефона'),
    BotCommand(command='/txexp', description='Экспорт пользователей в excel (csv)'),
    BotCommand(command='/userexp', description='Экспорт пользователей в excel (csv)'),
    BotCommand(command='/admsync', description='синхронизировать список администраторов с группой')
]
