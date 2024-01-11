from aiogram import Router
from aiogram.filters import Command
from . import chat, help, set_account, user_dialog, bcast, transaction, transaction_dialog, csv_export
from ...filters import AdminFilter

# top level commands
bcast_cmd = bcast.bcast_cmd
txl_cmd = transaction_dialog.txl_cmd
tx_cmd = transaction_dialog.tx_cmd
user_export_cmd = csv_export.users_export_cmd
tx_export_cmd = csv_export.tx_export_cmd
id_cmd = user_dialog.id_cmd
regs_cmd = user_dialog.regs_cmd
sync_cmd = chat.sync_cmd

# routers
admin_chat_router = chat.router
admin_help_router = help.router
admin_user_dialog_router = user_dialog.router
admin_bcast_router = bcast.router
admin_transaction_router = transaction.router
admin_transaction_dialog_router = transaction_dialog.router
admin_csv_export_router = csv_export.router
admin_set_account_router = set_account.router

admin_cmd_router = Router(name='admin_cmd_router')
admin_cmd_router.message.filter(AdminFilter())

admin_cmd_router.message.register(bcast_cmd, Command('bcast'))
admin_cmd_router.message.register(txl_cmd, Command('txl'))
admin_cmd_router.message.register(tx_cmd, Command('tx'))
admin_cmd_router.message.register(id_cmd, Command('id'))
admin_cmd_router.message.register(regs_cmd, Command('regs'))
admin_cmd_router.message.register(sync_cmd, Command('admsync'))
admin_cmd_router.message.register(user_export_cmd, Command('userexp'))
admin_cmd_router.message.register(tx_export_cmd, Command('txexp'))
