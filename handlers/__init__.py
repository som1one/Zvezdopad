import logging
from .common import register_common_handlers
from .user_commands import register_user_command_handlers
from .user_menu import register_user_menu_handlers  # Этот обработчик теперь содержит логику redirect_to_payment_bot
from .user_tasks import register_user_task_handlers
from .user_farm import register_user_farm_handlers
from .user_games import register_user_game_handlers
from .user_withdrawal import register_user_withdrawal_handlers  # Для обычных выводов, не Stars

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
from .admin_limits import register_admin_limits_handlers
from .inline_query import register_inline_handler
from .webapp_handler import register_webapp_handlers  # Если используется


def register_all_handlers(dp, bot, app):  # Убедитесь, что bot и app передаются
    log = logging.getLogger('handlers')
    log.info("Registering all handlers for main bot...")

    register_webapp_handlers(dp, bot)  # bot
    register_common_handlers(dp, bot)  # bot
    register_user_command_handlers(dp, bot)  # bot
    register_user_menu_handlers(dp, bot)  # bot (важно, что bot передается)
    register_user_task_handlers(dp, bot)  # bot
    register_user_farm_handlers(dp, bot)  # bot
    register_user_game_handlers(dp, bot)  # bot
    register_user_withdrawal_handlers(dp, bot, app)  # bot, app

    register_user_promocode_handlers(dp, bot)  # bot
    register_admin_panel_handlers(dp, bot, app)  # bot, app
    register_admin_user_handlers(dp, bot)  # bot
    register_admin_broadcast_handlers(dp, bot)  # bot
    register_admin_channel_handlers(dp, bot)  # bot
    register_admin_task_handlers(dp, bot)  # bot
    register_admin_promocode_handlers(dp, bot)  # bot
    register_admin_op_handlers(dp, bot)  # bot
    register_admin_withdrawal_handlers(dp, bot, app)  # bot, app
    register_admin_other_handlers(dp, bot, app)  # bot, app
    register_admin_limits_handlers(dp, bot)  # bot
    register_inline_handler(dp, bot)  # bot

    log.info("All main bot handlers registered.")
