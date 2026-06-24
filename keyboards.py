import logging
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo  # Если используется где-то еще
)
# Ваши импорты (убедитесь, что они корректны для вашего проекта)
from database import (
    are_withdrawals_enabled,
    are_referrals_enabled
)
from utils import t
# PAYMENT_BOT_USERNAME должен быть именем пользователя ВАШЕГО ПЛАТЕЖНОГО БОТА (без @)
# Убедитесь, что он определен в settings.py
from settings import LINK_5, USER_BOT, DONATE_PAY, PAYMENT_BOT_USERNAME

log = logging.getLogger(__name__)


def get_main_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)

    earn_text = t(user_id, 'btn_earn_stars_text')
    # Новый текст для кнопки, ведущей к платежному боту
    payment_and_boost_text = t(user_id, 'btn_redirect_to_payment_bot_text')
    if payment_and_boost_text == f"MISSING_TEXT_btn_redirect_to_payment_bot_text":  # Фоллбэк
        payment_and_boost_text = "💰 Баланс/Буст (Stars)"

    withdraw_text = t(user_id, 'btn_withdraw_stars_text')  # Для обычного вывода
    balance_text = t(user_id, 'btn_my_balance_text')
    tasks_text = t(user_id, 'btn_tasks_text')
    # spons_text = t(user_id, "btn_spons_text") # Старый текст кнопки "Буст", больше не нужен напрямую
    game_text = t(user_id, "btn_game_text")
    faq_text = t(user_id, "btn_faq_text")
    top_ref_text = t(user_id, "btn_top_ref_text")
    farm_text = t(user_id, "btn_farm_text")

    reklama_button = InlineKeyboardButton("💌 Отзывы", url=LINK_5)
    farm_button = InlineKeyboardButton(farm_text, callback_data="click_star")
    game_button = InlineKeyboardButton(game_text, callback_data="mini_games")

    # --- ИЗМЕНЕННАЯ КНОПКА ---
    # Старая кнопка spons_button с callback_data="donate" заменяется на новую:
    payment_and_boost_button = InlineKeyboardButton(payment_and_boost_text, callback_data="redirect_to_payment_bot")
    # -------------------------

    earn_button = InlineKeyboardButton(earn_text, callback_data="earn_stars")
    balance_button = InlineKeyboardButton(balance_text, callback_data="my_balance")
    tasks_button = InlineKeyboardButton(tasks_text, callback_data="tasks")
    exchange_button = InlineKeyboardButton(withdraw_text, callback_data="withdraw_stars_menu")  # Для обычного вывода
    faq_button = InlineKeyboardButton(faq_text, callback_data="faq")
    top_ref_button = InlineKeyboardButton(top_ref_text, callback_data="top_5")

    markup.add(farm_button)
    markup.add(earn_button)
    markup.row(balance_button, exchange_button)
    markup.row(tasks_button, faq_button)
    # --- ИСПОЛЬЗУЕМ НОВУЮ КНОПКУ ВМЕСТО СТАРОЙ 'spons_button' ---
    markup.row(payment_and_boost_button, game_button)
    # ----------------------------------------------------------
    markup.row(top_ref_button, reklama_button)
    return markup


def create_back_button(user_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(t(user_id, 'btn_back'), callback_data="back_main")


# Новая клавиатура для сообщения с выбором действия в платежном боте
def get_redirect_to_payment_bot_keyboard(user_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)

    # Тексты для кнопок (добавьте ключи в texts.py)
    text_topup = t(user_id, 'btn_redirect_topup_text')
    if text_topup == "MISSING_TEXT_btn_redirect_topup_text":
        text_topup = "💳 Пополнить баланс (Stars)"

    text_boost = t(user_id, 'btn_redirect_boost_text')
    if text_boost == "MISSING_TEXT_btn_redirect_boost_text":
        text_boost = "🚀 Купить буст (Stars)"

    # Формируем URL для deep linking
    # PAYMENT_BOT_USERNAME должен быть импортирован из settings.py
    payment_bot_link_topup = f"https://t.me/{PAYMENT_BOT_USERNAME}?start=topup"
    payment_bot_link_boost = f"https://t.me/{PAYMENT_BOT_USERNAME}?start=boost"

    markup.add(InlineKeyboardButton(text=text_topup, url=payment_bot_link_topup))
    markup.add(InlineKeyboardButton(text=text_boost, url=payment_bot_link_boost))
    markup.add(create_back_button(user_id))  # Кнопка "Назад в главное меню" основного бота
    return markup


def generate_pagination_buttons(user_id, page, total_pages):
    markup = InlineKeyboardMarkup(row_width=2)
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(
            InlineKeyboardButton(
                f"⬅️ Назад. стр. {page - 1}",
                callback_data=f"referrals_page:{page - 1}"
            )
        )
    if page < total_pages:
        pagination_buttons.append(
            InlineKeyboardButton(
                f"➡️ След. стр. {page + 1}",
                callback_data=f"referrals_page:{page + 1}"
            )
        )
    if pagination_buttons:
        markup.row(*pagination_buttons)
    giftday_text = t(user_id, "btn_giftday_text")  # Убедитесь, что ключ есть в texts.py
    if giftday_text == "MISSING_TEXT_btn_giftday_text": giftday_text = "🎁 Ежедневка"

    promo_text = t(user_id, "btn_promo_text")  # Убедитесь, что ключ есть в texts.py
    if promo_text == "MISSING_TEXT_btn_promo_text": promo_text = "🎫 Промокод"

    promocode_button = InlineKeyboardButton(promo_text, callback_data="enter_promocode")
    giftday_button = InlineKeyboardButton(giftday_text, callback_data="giftday")
    markup.row(promocode_button, giftday_button)
    markup.add(create_back_button(user_id))
    return markup


def get_mini_games_keyboard(user_id, wheel_url: str):  # wheel_url передается из user_games.py
    keyboard = InlineKeyboardMarkup(row_width=2)
    # Кнопка для WebApp Колеса Фортуны
    if wheel_url:  # Добавляем кнопку только если URL передан
        keyboard.add(
            InlineKeyboardButton(
                "🎡 Колесо Фортуны",
                web_app=WebAppInfo(url=wheel_url)
            )
        )
    else:  # Если URL нет, можно добавить плейсхолдер или другую кнопку
        log.warning("wheel_url не передан в get_mini_games_keyboard")
        # keyboard.add(InlineKeyboardButton("🎡 Колесо (недоступно)", callback_data="wheel_unavailable"))

    keyboard.insert(InlineKeyboardButton("🎲 Все или ничего", callback_data="play_game"))
    keyboard.insert(InlineKeyboardButton("🏃‍♂️ Я вор!", callback_data="play_robbery"))
    keyboard.add(InlineKeyboardButton("🎰 Слоты", callback_data="play_slots"))
    keyboard.add(create_back_button(user_id))
    return keyboard


def get_luck_game_keyboard(user_id):
    keyboard = InlineKeyboardMarkup(row_width=3)
    stakes = [0.5, 1, 2, 3, 4, 5]  # Убедитесь, что эти ставки актуальны
    buttons = [
        InlineKeyboardButton(
            f"Ставка: {stake} ⭐",
            callback_data=f"play_game_with_bet:{stake}"
        )
        for stake in stakes
    ]
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton("⬅️ Назад в меню игр", callback_data="mini_games"))
    return keyboard


def create_slot_button(user_id):  # user_id может быть не нужен, если кнопка всегда одинаковая
    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton("🎰 Крутить", callback_data="play_slots")  # play_slots - это для входа в игру Слоты
    keyboard.add(button)
    return keyboard


def create_bet_inline_keyboard(user_id):  # user_id может быть не нужен
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.row(
        InlineKeyboardButton("1 ⭐️", callback_data="bets_1"),
        InlineKeyboardButton("2 ⭐️", callback_data="bets_2"),
        InlineKeyboardButton("3 ⭐️", callback_data="bets_3")
    )
    keyboard.row(
        InlineKeyboardButton("4 ⭐️", callback_data="bets_4"),
        InlineKeyboardButton("5 ⭐️", callback_data="bets_5"),
        InlineKeyboardButton("6 ⭐️", callback_data="bets_6")
    )
    keyboard.add(InlineKeyboardButton("⬅️ Назад в меню игр", callback_data="mini_games"))
    return keyboard


# --- Админские клавиатуры ---
async def create_admin_panel_markup(user_id: int) -> InlineKeyboardMarkup:  # Делаем async, так как внутри await
    admin_markup = InlineKeyboardMarkup(row_width=2)  # Изменил на 2 для более компактного вида

    # Асинхронное получение статусов
    withdraw_enabled = await are_withdrawals_enabled()
    referrals_enabled = await are_referrals_enabled()

    withdraw_toggle_text = t(user_id, 'btn_admin_withdraw_enable') if withdraw_enabled else t(user_id,
                                                                                              'btn_admin_withdraw_disable')
    referral_toggle_text = t(user_id, 'btn_admin_referral_enable') if referrals_enabled else t(user_id,
                                                                                               'btn_admin_referral_disable')

    admin_markup.row(
        InlineKeyboardButton(text="📨 Рассылка", callback_data="admin_mailing"),
        InlineKeyboardButton(text="✉️ Сообщение юзеру", callback_data="admin_direct_message_user")
    )
    admin_markup.row(
        InlineKeyboardButton(text="🔎 Инфо о юзере", callback_data="get_user_id"),
        InlineKeyboardButton(text="🎁 Выдать звезды всем", callback_data="dobavlenie")
    )
    admin_markup.row(
        InlineKeyboardButton(text="🗑 Обнулить балансы", callback_data="obnylenie"),
        InlineKeyboardButton(text="🔗 Создать спецссылку", callback_data="gen_link")
    )
    admin_markup.row(
        InlineKeyboardButton(text="⚙️ Настройка лимитов", callback_data="admin_limits_menu"),
        InlineKeyboardButton(text="⏰ Счастливое время", callback_data="admin_lucky_time")
    )
    admin_markup.add(InlineKeyboardButton(text="🏆 Выбор Ежедн. Подарка", callback_data="admin_select_daily_gift"))
    admin_markup.add(InlineKeyboardButton(text="📦 Экспорт Базы", callback_data="admin_db"))

    admin_markup.add(InlineKeyboardButton(text="--- Промокоды ---", callback_data="no_action_promo"))
    admin_markup.row(
        InlineKeyboardButton(text="➕ Создать промо", callback_data="admin_promocode_added"),
        InlineKeyboardButton(text="📊 Список промо", callback_data="show_promocodes")
    )
    admin_markup.add(InlineKeyboardButton(text="--- Каналы ОП ---", callback_data="no_action_channels"))
    admin_markup.row(
        InlineKeyboardButton(text="➕ Добавить канал ОП", callback_data="admin_add_channel"),
        InlineKeyboardButton(text="📚 Список каналов ОП", callback_data="admin_get_channels")
    )
    admin_markup.add(InlineKeyboardButton(text="⚠️ Кнопки ОП (без проверки)", callback_data="op"))

    admin_markup.add(InlineKeyboardButton(text="--- Задания ---", callback_data="no_action_tasks"))
    admin_markup.row(
        InlineKeyboardButton(text="➕ Добавить задание", callback_data="admin_add_task"),
        InlineKeyboardButton(text="📋 Список заданий", callback_data="show_tasks")
    )
    admin_markup.add(InlineKeyboardButton(text="📊 Прогресс заданий", callback_data="taskslist"))

    admin_markup.add(InlineKeyboardButton(text="--- Выплаты (старый механизм) ---", callback_data="no_action_withdraw"))
    admin_markup.row(
        InlineKeyboardButton("✅ Принять все", callback_data="paid_all"),
        InlineKeyboardButton("🚫 Отклонить все", callback_data="denied_all")
    )
    admin_markup.row(
        InlineKeyboardButton(withdraw_toggle_text, callback_data="toggle_withdrawals"),
        InlineKeyboardButton(referral_toggle_text, callback_data="toggle_referrals")
    )
    admin_markup.add(InlineKeyboardButton("🔧 Тех. работы", callback_data="admin_maintenance"))
    return admin_markup


async def create_admin_limits_menu(wheel_ref_req: int, wheel_daily_limit: int, exchange_ref_req: int,
                                   exchange_daily_limit: int) -> InlineKeyboardMarkup:  # Добавил async
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(f"🎡 Реф. Колесо: {wheel_ref_req} (изменить)",
                             callback_data="edit_limit:wheel_referral_req"),
        InlineKeyboardButton(f"🎡 Лимит Колесо/день: {wheel_daily_limit} (изменить)",
                             callback_data="edit_limit:wheel_daily_limit"),
        InlineKeyboardButton(f"🔄 Реф. Обмен: {exchange_ref_req} (изменить)",
                             callback_data="edit_limit:exchange_referral_req"),
        InlineKeyboardButton(f"🔄 Лимит Обмен/день: {exchange_daily_limit} (изменить)",
                             callback_data="edit_limit:exchange_daily_limit")
    )
    markup.add(InlineKeyboardButton(text="👑 Админ-меню", callback_data="adminpanel"))
    return markup


def create_admin_limits_cancel_markup() -> InlineKeyboardMarkup:  # Остается sync
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="⬅️ Назад в меню лимитов", callback_data="admin_limits_menu"))
    return keyboard


def create_inline_menu() -> InlineKeyboardMarkup:  # Остается sync
    keyboard = InlineKeyboardMarkup(row_width=1)
    button1 = InlineKeyboardButton("🗃 Полную базу данных (.db)",
                                   callback_data="full_db")  # Эта логика для SQLite, для PG будет другой механизм
    button2 = InlineKeyboardButton("📁 Список Username (.txt)", callback_data="usernames_list")
    button3 = InlineKeyboardButton("📁 Список ID (.txt)", callback_data="ids_list")
    button4 = InlineKeyboardButton("👑 Вернуться в админ-меню", callback_data="adminpanel")
    keyboard.add(button1, button2, button3, button4)
    return keyboard


def create_admin_cancel_markup(callback_data="adminpanel") -> InlineKeyboardMarkup:  # Остается sync
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="👑 Админ-меню", callback_data=callback_data))
    return keyboard


def create_cancel_direct_message_markup() -> InlineKeyboardMarkup:  # Остается sync
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_direct_message"))
    return markup


def create_broadcast_confirmation_markup() -> InlineKeyboardMarkup:  # Остается sync
    confirm_keyboard = InlineKeyboardMarkup(row_width=2)
    confirm_keyboard.add(InlineKeyboardButton("✅ Отправить", callback_data="confirm_broadcast"))
    confirm_keyboard.add(InlineKeyboardButton("✏️ Изменить", callback_data="edit_broadcast"))
    confirm_keyboard.add(InlineKeyboardButton("❌ Отменить рассылку", callback_data="cancell_ras"))
    return confirm_keyboard


def create_broadcast_progress_markup() -> InlineKeyboardMarkup:  # Остается sync
    keyboards = InlineKeyboardMarkup()
    keyboards.add(InlineKeyboardButton("❌ Остановить рассылку", callback_data="stop_broadcast"))
    return keyboards


def create_hide_message_markup(uid: int) -> InlineKeyboardMarkup:  # Остается sync
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("❌ Скрыть", callback_data=f"hide_message_{uid}"))
    return keyboard


def create_profile_actions_markup(user_id_to_show: int, block_status_str: str) -> InlineKeyboardMarkup:  # Остается sync
    keyboard = InlineKeyboardMarkup(row_width=2)
    profile_url = f"tg://user?id={user_id_to_show}"
    if "Заблокирован" in block_status_str:
        block_unblock_btn = InlineKeyboardButton(text="🔓 Разблок", callback_data=f"unblock_{user_id_to_show}")
    else:
        block_unblock_btn = InlineKeyboardButton(text="🔒 Заблок", callback_data=f"block_{user_id_to_show}")
    add_stars_btn = InlineKeyboardButton(text="➕ Добавить ⭐", callback_data=f"add_stars_{user_id_to_show}")
    subtract_stars_btn = InlineKeyboardButton(text="➖ Списать ⭐", callback_data=f"subtract_stars_{user_id_to_show}")
    profile_btn = InlineKeyboardButton(text="👤 Профиль", url=profile_url)
    clickup_btn = InlineKeyboardButton(text="🖱️ Награда клик", callback_data=f"set_click_reward_for_{user_id_to_show}")
    ref_reward_btn = InlineKeyboardButton(text="🔗 Награда реф", callback_data=f"set_ref_reward_for_{user_id_to_show}")
    keyboard.add(block_unblock_btn)
    keyboard.add(add_stars_btn, subtract_stars_btn)
    keyboard.add(profile_btn)
    keyboard.add(clickup_btn, ref_reward_btn)
    keyboard.add(InlineKeyboardButton(text="👑 Админ-меню", callback_data="adminpanel"))
    return keyboard


def create_withdrawal_buttons(user_id: int, stars: float) -> InlineKeyboardMarkup:  # Остается sync
    markup = InlineKeyboardMarkup(row_width=2)
    # Этот список для ВЫВОДА (не пополнения Stars)
    amounts = [
        (15, "🧸", 5170233102089322756), (15, "💝", 5170145012310081615),
        (25, "🌹", 5168103777563050263), (25, "🎁", 5170250947678437525),
        (50, "🍾", 6028601630662853006), (50, "🚀", 5170564780938756245),
        (50, "💐", 5170314324215857265), (50, "🎂", 5170144170496491616),
        (100, "🏆", 5168043875654172773), (100, "💍", 5170690322832818290),
        (100, "💎", 5170521118301225164),
        # (1700, "📱", None) # Пример для Premium, если он выводится не через Stars
    ]
    row_buttons = []
    for amt, emoji, star_gift_id in amounts:
        is_available = stars >= amt
        button_text = f"{amt} ⭐ ({emoji})" if is_available else f"{amt} ⭐ ({emoji}) 🔒"
        button_callback = f"withdraw:{amt}:{star_gift_id}" if is_available else "insufficient_funds"
        row_buttons.append(InlineKeyboardButton(text=button_text, callback_data=button_callback))
        if len(row_buttons) == 2:
            markup.row(*row_buttons)
            row_buttons = []
    if row_buttons:
        markup.row(*row_buttons)

    # Пример для Premium, если он выводится НЕ через Stars
    # premium_amt = 1700
    # if any(a[0] == premium_amt for a in amounts): # Если Premium уже есть в списке gifts, не добавляем отдельно
    #     pass
    # else:
    #     is_premium_available = stars >= premium_amt
    #     prem_button_text = f"Premium 6 мес. ({premium_amt}⭐)" if is_premium_available else f"Premium 6 мес. ({premium_amt}⭐) 🔒"
    #     prem_button_callback = f"withdraw:{premium_amt}:premium_other" if is_premium_available else "insufficient_funds"
    #     markup.add(InlineKeyboardButton(text=prem_button_text, callback_data=prem_button_callback))

    markup.add(create_back_button(user_id))
    return markup


def create_admin_withdrawal_markup(user_id_req: int, amt: float, emoji: str, request_id: int,
                                   message_id=None) -> InlineKeyboardMarkup:  # Остается sync
    inline_keyboard = InlineKeyboardMarkup(row_width=2)
    deny_callback = f"denied_req:{request_id}"
    paid_callback = f"paid:{user_id_req}:{int(amt)}:{emoji}:{request_id}"  # Убедимся, что amt - int для callback
    inline_keyboard.row(
        InlineKeyboardButton("✅ Отправить", callback_data=paid_callback),
        InlineKeyboardButton("🚫 Отказать", callback_data=deny_callback)
    )
    inline_keyboard.add(InlineKeyboardButton("👤 Профиль пользователя", url=f"tg://user?id={user_id_req}"))
    return inline_keyboard


def create_admin_task_list_markup(tasks: list,
                                  bot_instance) -> InlineKeyboardMarkup:  # bot_instance может быть не нужен, если имена каналов не получаем
    keyboard = InlineKeyboardMarkup(row_width=1)
    if tasks:
        for task_info in tasks:
            try:
                # Адаптируем под структуру данных из asyncpg.Record (если она как dict)
                task_id = task_info.get('id')
                channel_id_val = task_info.get('channel_id')  # Может быть int или str
                reward = task_info.get('reward')
                active = task_info.get('active')
                task_type = task_info.get('task_type')
                completed = task_info.get('completed_count', 0)
                limit = task_info.get('max_completions', '?')

                status = "🟩 Активно" if active else "🟥 Неактивно"
                type_str = "Ссылка" if task_type == "nosub" else "Канал/Чат"
                target_str = str(channel_id_val)
                display_target = target_str if len(target_str) <= 25 else target_str[:22] + "..."
                button_text = f"{status} | {type_str}: {display_target} | {reward}⭐ | {completed}/{limit} | ❌"
                delete_button = InlineKeyboardButton(text=button_text, callback_data=f"delete_task_btn_{task_id}")
                keyboard.add(delete_button)
            except Exception as e:
                log.error(f"Error processing task for admin list: {task_info}, error: {e}")
                task_id_str = str(task_info.get('id')) if isinstance(task_info, dict) else '?'
                keyboard.add(InlineKeyboardButton(f"Ошибка задания ID: {task_id_str}", callback_data="no_action"))
    else:
        keyboard.add(InlineKeyboardButton("Нет активных заданий", callback_data="no_action"))
    keyboard.add(InlineKeyboardButton(text="👑 Вернуться в админ-меню", callback_data="adminpanel"))
    return keyboard

