# Содержимое файла: handlers/__init__.py (Обновлено с admin_limits)
import logging

# Импортируем функции регистрации из каждого модуля обработчиков
from .common import register_common_handlers
from .user_commands import register_user_command_handlers
from .user_menu import register_user_menu_handlers
from .user_tasks import register_user_task_handlers
from .user_farm import register_user_farm_handlers
from .user_games import register_user_game_handlers
from .user_withdrawal import register_user_withdrawal_handlers
from .user_donations import register_user_donation_handlers
from .user_promocodes import register_user_promocode_handlers
from .admin_panel import register_admin_panel_handlers
from .admin_users import register_admin_user_handlers
from .admin_broadcast import register_admin_broadcast_handlers
from .admin_channels import register_admin_channel_handlers
from .admin_tasks import register_admin_task_handlers
from .admin_promocodes import register_admin_promocode_handlers
from .admin_op import register_admin_op_handlers
from .admin_withdrawal import register_admin_withdrawal_handlers
from .admin_other import register_admin_other_handlers
from .inline_query import register_inline_handler
from .webapp_handler import register_webapp_handlers
from .admin_limits import register_admin_limits_handlers
from .admin_maintenance import register_admin_maintenance_handlers
from .admin_referrals import register_admin_referral_handlers
from .admin_proxy import register_admin_proxy_handlers
from .user_proxy import register_user_proxy_handlers
from .user_flyer_tasks import register_user_flyer_handlers


# --------------------


def register_all_handlers(dp, bot, app):
    """Регистрирует все обработчики в диспетчере."""
    log = logging.getLogger('handlers')
    log.info("Registering all handlers...")

    register_webapp_handlers(dp, bot)
    register_common_handlers(dp, bot)
    register_user_command_handlers(dp, bot)
    register_user_menu_handlers(dp, bot)
    register_user_task_handlers(dp, bot)
    register_user_farm_handlers(dp, bot)
    register_user_game_handlers(dp, bot)
    register_user_withdrawal_handlers(dp, bot, app)
    register_user_donation_handlers(dp, bot)
    register_user_promocode_handlers(dp, bot)
    register_admin_panel_handlers(dp, bot, app)
    register_admin_user_handlers(dp, bot)
    register_admin_broadcast_handlers(dp, bot)
    register_admin_channel_handlers(dp, bot)
    register_admin_task_handlers(dp, bot)
    register_admin_promocode_handlers(dp, bot)
    register_admin_op_handlers(dp, bot)
    register_admin_withdrawal_handlers(dp, bot, app)
    register_admin_other_handlers(dp, bot, app)
    register_inline_handler(dp, bot)
    register_admin_limits_handlers(dp, bot)
    register_admin_maintenance_handlers(dp, bot)
    register_admin_referral_handlers(dp, bot)
    register_admin_proxy_handlers(dp, bot)
    register_user_proxy_handlers(dp, bot)
    register_user_flyer_handlers(dp, bot)

    log.info("All handlers registered.")
