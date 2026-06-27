# Содержимое файла: C:\Users\Igroman\Desktop\new\states.py
from aiogram.dispatcher.filters.state import State, StatesGroup


class GiveStars(StatesGroup):
    amount = State()


class AdminSearchIdlState(StatesGroup):
    waiting_for_message = State()


class PromoCodeState(StatesGroup):
    waiting_for_promocode = State()


class BroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_button_text = State()
    waiting_for_button_url = State()
    waiting_for_more_buttons = State()
    waiting_for_confirmation = State()


class ProjectBalanceState(StatesGroup):
    waiting_for_balance = State()


class AdminAddChannelState(StatesGroup):
    waiting_for_channel_id = State()
    waiting_for_delete_time = State()


class AdminDeleteChannelState(StatesGroup):
    waiting_for_channel_id = State()


class AdminAddTaskState(StatesGroup):
    waiting_for_task_type = State()
    waiting_for_channel_id = State()
    waiting_for_reward = State()
    waiting_for_max_completions = State()


class AdminRemoveTaskState(StatesGroup):
    waiting_for_channel_id = State()

class AdminDirectMessageState(StatesGroup):
    waiting_for_username = State()
    waiting_for_message_content = State()
    waiting_for_buttons = State()
    waiting_for_confirmation = State()

class AdminAddStarsState(StatesGroup):
    waiting_for_data = State()


class AdminAddPromoCodeState(StatesGroup):
    waiting_for_data = State()


class AdminDeletePromoCodeState(StatesGroup):
    waiting_for_promocode = State()


class UserIDState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_star_amount = State()
    waiting_for_ref_reward = State()
    waiting_for_click_reward = State()


class ButtonState(StatesGroup):
    adding = State()
    removing = State()


class SlotState(StatesGroup):
    waiting_for_bet = State()


class AdminSetBalanceState(StatesGroup):
    waiting_for_balance = State()


class AdminLimitsState(StatesGroup):
    waiting_for_wheel_ref_req = State()
    waiting_for_wheel_daily_limit = State()
    waiting_for_exchange_daily_limit = State()
    # waiting_for_exchange_ref_req = State()
    waiting_for_exchange_referral_req = State()
    waiting_for_streak_days_required = State()
    waiting_for_streak_reward = State()


class MaintenanceState(StatesGroup):
    waiting_for_message = State()
    waiting_for_end_text = State()


class MiniAppCaptchaState(StatesGroup):
    waiting_for_answer = State()


class AdminAddProxyState(StatesGroup):
    waiting_for_proxy_data = State()
