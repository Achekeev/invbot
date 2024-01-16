import dotenv
from os import environ as env

# load .env
dotenv.load_dotenv()

DEV = True

REVERSE_PROXIES   = [['127.0.0.1', '::1']]
WHITE_PATHS       = ['/bithide']
BITHIDE_SERVER_IP = ['127.0.0.1', '::1']

HTTP_HOST = env.get('HTTP_HOST', '127.0.0.1')
HTTP_PORT = int(env.get('HTTP_PORT', 8011))

# BitHide
BITHIDE_URL            = env.get('BITHIDE_URL', 'https://demo.bithide.io:8645')
BIHIDE_PUBLIC_KEY      = env.get('BITHIDE_PUBLIC_KEY')
BITHIDE_CALLBACK_MOUNT = env.get('BITHIDE_CALLBACK_MOUNT', '/bithide')
BITHIDE_CALLBACK_URL   = env.get('BITHIDE_CALLBACK_URL')
BITHIDE_PAYOUT_WALLET  = env.get('BITHIDE_PAYOUT_WALLET')
BITHIDE_AUTO_PAYOUT    = int(env.get('BITHIDE_AUTO_PAYOUT', 1))

# webhook
WEBHOOK_URL    = env.get('WEBHOOK_URL')
WEBHOOK_PATH   = env.get('WEBHOOK_PATH', '/bot')
WEBHOOK_SECRET = env.get('WEBHOOK_SECRET')

# currencies
CURRENCIES = ['USDT-TRC20', 'KGS']
SPECIAL = ['KGS']

# config
BOT_TOKEN      = env.get('BOT_TOKEN')
DB_URL         = env.get('DB_URL', "sqlite+aiosqlite:///data/bot.sqlite")
REDIS_URL      = env.get('REDIS_URL')
REDIS_LIFETIME = int(env.get('REDIS_LIFETIME', 7*24*3600))

LOGLEVEL      = env.get('LOGLEVEL', 'INFO')
SQL_LOG_LEVEL = env.get('LOGLEVEL', 'WARN')

# predefined admins (not implemented)
ADMINS_CHAT_ID = env.get("ADMINS_CHAT_ID")

# Pause per message for bulk send (broadcasts)
BCAST_PAUSE = 0.2

DATE_FORMAT = '%d.%m.%Y'
DATETIME_FORMAT = '%d.%m.%Y %H:%M:%S'

EXT_ID_LIST_SIZE = 100
