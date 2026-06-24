# Содержимое файла: keyboards.py (С переносом кнопок и прошлыми правками)
import logging
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo
)

from database import (
    get_wheel_referral_req, get_wheel_daily_limit, get_exchange_daily_limit,
    get_exchange_referral_req, are_withdrawals_enabled, are_referrals_enabled
)
# Импортируем утилиты и настройки
from utils import t
from settings import LINK_5, USER_BOT, DONATE_PAY

log = logging.getLogger(__name__)


def get_main_menu_markup(user_id):
    """Создает клавиатуру главного меню (Inline)."""
    markup = InlineKeyboardMarkup(row_width=2)

    earn_text = t(user_id, 'btn_earn_stars_text')
    withdraw_text = t(user_id, 'btn_withdraw_stars_text')
    balance_text = t(user_id, 'btn_my_balance_text')
    tasks_text = t(user_id, 'btn_tasks_text')
    spons_text = t(user_id, "btn_spons_text")
    game_text = t(user_id, "btn_game_text")  # Название кнопки
    faq_text = t(user_id, "btn_faq_text")
    top_ref_text = t(user_id, "btn_top_ref_text")
    farm_text = t(user_id, "btn_farm_text")

    reklama_button = InlineKeyboardButton("💌 Отзывы", url=LINK_5)
    farm_button = InlineKeyboardButton(farm_text, callback_data="click_star")
    # Возвращаем callback_data="mini_games" для Inline кнопки
    game_button = InlineKeyboardButton(game_text, callback_data="mini_games")
    spons_button = InlineKeyboardButton(spons_text, callback_data="donate")
    earn_button = InlineKeyboardButton(earn_text, callback_data="earn_stars")
    balance_button = InlineKeyboardButton(balance_text, callback_data="my_balance")
    tasks_button = InlineKeyboardButton(tasks_text, callback_data="tasks")
    exchange_button = InlineKeyboardButton(withdraw_text, callback_data="withdraw_stars_menu")
    faq_button = InlineKeyboardButton(faq_text, callback_data="faq")
    top_ref_button = InlineKeyboardButton(top_ref_text, callback_data="top_5")

    markup.add(farm_button)
    markup.add(earn_button)
    markup.row(balance_button, exchange_button)
    markup.row(tasks_button, faq_button)
    markup.row(spons_button, game_button)
    markup.row(top_ref_button, reklama_button)

    return markup


def create_back_button(user_id):
    """Создает кнопку 'Назад в главное меню' (Inline)."""
    return InlineKeyboardButton(t(user_id, 'btn_back'), callback_data="back_main")


def generate_pagination_buttons(user_id, page, total_pages):
    """Создает клавиатуру для пагинации и доп. кнопок в профиле."""
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

    giftday_text = t(user_id, "btn_giftday_text")
    promo_text = t(user_id, "btn_promo_text")
    promocode_button = InlineKeyboardButton(promo_text, callback_data="enter_promocode")
    giftday_button = InlineKeyboardButton(giftday_text, callback_data="giftday")
    markup.row(promocode_button, giftday_button)
    markup.add(create_back_button(user_id))
    return markup


# --- Inline клавиатура для игр ---


def get_mini_games_keyboard(user_id, wheel_url: str):
    """Создает Inline клавиатуру для меню мини-игр."""
    keyboard = InlineKeyboardMarkup(row_width=2)  # Можно 2 в ряд

    # Кнопка WebApp для Колеса Фортуны
    keyboard.add(
        InlineKeyboardButton(
            "🎡 Колесо Фортуны",
            web_app=WebAppInfo(url=wheel_url)  # Запускаем Mini App через Inline кнопку
        )
    )
    # Кнопки для других игр с callback_data
    keyboard.insert(InlineKeyboardButton("🎲 Все или ничего", callback_data="play_game"))
    keyboard.insert(InlineKeyboardButton("🏃‍♂️ Я вор!", callback_data="play_robbery"))
    keyboard.add(InlineKeyboardButton("🎰 Слоты", callback_data="play_slots"))
    # Кнопка Назад в главное меню
    keyboard.add(create_back_button(user_id))  # callback_data="back_main"
    return keyboard


def get_luck_game_keyboard(user_id):
    """Создает клавиатуру для игры 'Испытать удачу' (Inline)."""
    keyboard = InlineKeyboardMarkup(row_width=3)
    stakes = [0.5, 1, 2, 3, 4, 5]
    buttons = [
        InlineKeyboardButton(
            f"Ставка: {stake} ⭐",
            callback_data=f"play_game_with_bet:{stake}"
        )
        for stake in stakes
    ]
    keyboard.add(*buttons)
    # Кнопка Назад возвращает в inline меню игр
    keyboard.add(InlineKeyboardButton("⬅️ Назад в меню игр", callback_data="mini_games"))
    return keyboard


def create_slot_button(user_id):
    """Создает кнопку для игры в слоты (Inline)."""
    keyboard = InlineKeyboardMarkup()
    button = InlineKeyboardButton("🎰 Крутить", callback_data="play_slots")  # Этот колбэк остается для игры
    keyboard.add(button)
    return keyboard


def create_bet_inline_keyboard(user_id):
    """Создает клавиатуру для выбора ставки в слотах (Inline)."""
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
    # Кнопка Назад возвращает в inline меню игр
    keyboard.add(InlineKeyboardButton("⬅️ Назад в меню игр", callback_data="mini_games"))
    return keyboard


# --- Остальные функции генерации клавиатур (admin, withdrawal...) ---


def create_admin_panel_markup(user_id):
    """Создает клавиатуру админ-панели (Новая структура + кнопки toggles)."""
    admin_markup = InlineKeyboardMarkup(row_width=1)  # Начинаем с ширины 1

    # Получаем текущие состояния для кнопок
    withdraw_enabled = are_withdrawals_enabled()
    referrals_enabled = are_referrals_enabled()

    # Тексты для кнопок
    withdraw_toggle_text = t(user_id, 'btn_admin_withdraw_enable') if withdraw_enabled else t(user_id,
                                                                                              'btn_admin_withdraw_disable')
    referral_toggle_text = t(user_id, 'btn_admin_referral_enable') if referrals_enabled else t(user_id,
                                                                                               'btn_admin_referral_disable')

    # Определяем все кнопки
    search_id = InlineKeyboardButton(text="🔎 Инфо о юзере", callback_data="get_user_id")
    mailing_btn = InlineKeyboardButton(text="📨 Рассылка", callback_data="admin_mailing")
    admin_db_btn = InlineKeyboardButton(text="📦 База данных", callback_data="admin_db")
    dobavlenie = InlineKeyboardButton(text="🎁 Выдать звезды всем", callback_data="dobavlenie")
    obnylenie = InlineKeyboardButton(text="🗑 Обнулить балансы", callback_data="obnylenie")
    lucky_time_btn = InlineKeyboardButton(text="⏰ Счастливое время", callback_data="admin_lucky_time")
    admin_promo = InlineKeyboardButton(text="➕ Создать промо", callback_data="admin_promocode_added")
    show_promocodes = InlineKeyboardButton(text="📊 Список промо", callback_data="show_promocodes")
    admin_promo2 = InlineKeyboardButton(text="➖ Удалить промо", callback_data="admin_promocode_delete")
    add_channel_btn = InlineKeyboardButton(text="➕ Добавить канал ОП", callback_data="admin_add_channel")
    list_channel_btn = InlineKeyboardButton(text="📚 Список каналов ОП", callback_data="admin_get_channels")
    remove_channel_btn = InlineKeyboardButton(text="➖ Удалить канал ОП", callback_data="admin_delete_channel")
    add_task_btn = InlineKeyboardButton(text="➕ Добавить задание", callback_data="admin_add_task")
    list_tasks_btn = InlineKeyboardButton(text="📋 Список заданий", callback_data="show_tasks")
    remove_task_btn = InlineKeyboardButton(text="➖ Удалить задание", callback_data="admin_remove_task")
    taskslist_btn = InlineKeyboardButton(text="📊 Прогресс заданий", callback_data="taskslist")
    spec_ref_btn = InlineKeyboardButton(text="🔗 Создать спецссылку", callback_data="gen_link")
    add_noop_btn = InlineKeyboardButton(text="⚠️ Кнопки ОП без проверки", callback_data="op")
    accept_all_btn = InlineKeyboardButton("✅ Принять все заявки", callback_data="paid_all")
    deny_all_btn = InlineKeyboardButton("🚫 Отклонить все заявки", callback_data="denied_all")
    limits_btn = InlineKeyboardButton("⚙️ Настройка лимитов", callback_data="admin_limits_menu")
    daily_gift_btn = InlineKeyboardButton("🏆 Выбор Ежедн. Подарка", callback_data="admin_select_daily_gift")
    withdraw_toggle_btn = InlineKeyboardButton(withdraw_toggle_text, callback_data="toggle_withdrawals")
    referral_toggle_btn = InlineKeyboardButton(referral_toggle_text, callback_data="toggle_referrals")
    maintenance_btn = InlineKeyboardButton("🔧 Тех. работы", callback_data="admin_maintenance")

    admin_markup.row_width = 1
    admin_markup.add(mailing_btn)
    admin_markup.add(search_id)
    admin_markup.add(obnylenie)
    admin_markup.add(dobavlenie)
    admin_markup.add(spec_ref_btn)
    admin_markup.add(limits_btn)  # limits_btn и daily_gift_btn
    admin_markup.add(daily_gift_btn)
    admin_markup.row(admin_promo, show_promocodes, admin_promo2)  # Ширина 3
    admin_markup.row(add_channel_btn, list_channel_btn, remove_channel_btn)  # Ширина 3
    admin_markup.row(add_task_btn, list_tasks_btn, remove_task_btn)  # Ширина 3
    admin_markup.add(taskslist_btn)
    admin_markup.add(admin_db_btn)
    admin_markup.add(add_noop_btn)
    admin_markup.add(lucky_time_btn)
    admin_markup.row(accept_all_btn, deny_all_btn)
    admin_markup.row(withdraw_toggle_btn, referral_toggle_btn)
    admin_markup.add(maintenance_btn)

    return admin_markup


def create_admin_limits_menu():
    """Создает клавиатуру для меню настройки лимитов."""
    markup = InlineKeyboardMarkup(row_width=1)

    # Получаем текущие значения лимитов
    wheel_ref_req = get_wheel_referral_req()
    wheel_daily_limit = get_wheel_daily_limit()
    exchange_daily_limit = get_exchange_daily_limit()
    exchange_ref_req = get_exchange_referral_req()  # Получаем лимит рефов обмена

    # Создаем кнопки
    markup.add(
        InlineKeyboardButton(
            f"🎡 Реф. Колесо: {wheel_ref_req} (изменить)",
            callback_data="edit_limit:wheel_ref_req"
        ),
        InlineKeyboardButton(
            f"🎡 Лимит Колесо/день: {wheel_daily_limit} (изменить)",
            callback_data="edit_limit:wheel_daily_limit"
        ),
        InlineKeyboardButton(  # Добавлена кнопка для лимита реф обмена
            f"🔄 Реф. Обмен: {exchange_ref_req} (изменить)",
            callback_data="edit_limit:exchange_referral_req"
        ),
        InlineKeyboardButton(
            f"🔄 Лимит Обмен/день: {exchange_daily_limit} (изменить)",
            callback_data="edit_limit:exchange_daily_limit"
        )
    )
    markup.add(InlineKeyboardButton(text="👑 Админ-меню", callback_data="adminpanel"))
    return markup


def create_admin_limits_cancel_markup():
    """Создает клавиатуру отмены для FSM изменения лимита."""
    keyboard = InlineKeyboardMarkup()
    # Возврат в меню ЛИМИТОВ, а не в главное админ меню
    keyboard.add(InlineKeyboardButton(text="⬅️ Назад в меню лимитов", callback_data="admin_limits_menu"))
    return keyboard


def create_inline_menu():
    """Создает клавиатуру для выбора типа выгрузки БД."""
    keyboard = InlineKeyboardMarkup(row_width=1)
    button1 = InlineKeyboardButton("🗃 Полную базу данных (.db)", callback_data="full_db")
    button2 = InlineKeyboardButton("📁 Список Username (.txt)", callback_data="usernames_list")
    button3 = InlineKeyboardButton("📁 Список ID (.txt)", callback_data="ids_list")
    button4 = InlineKeyboardButton("👑 Вернуться в админ-меню", callback_data="adminpanel")
    keyboard.add(button1, button2, button3, button4)
    return keyboard


def create_admin_cancel_markup(callback_data="adminpanel"):
    """Создает клавиатуру с кнопкой отмены/возврата в админ панель."""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(text="👑 Админ-меню", callback_data=callback_data))
    return keyboard


def create_broadcast_confirmation_markup():
    """Создает клавиатуру подтверждения рассылки."""
    confirm_keyboard = InlineKeyboardMarkup(row_width=2)
    confirm_keyboard.add(InlineKeyboardButton("✅ Отправить", callback_data="confirm_broadcast"))
    confirm_keyboard.add(InlineKeyboardButton("✏️ Изменить", callback_data="edit_broadcast"))
    confirm_keyboard.add(InlineKeyboardButton("❌ Отменить рассылку", callback_data="cancell_ras"))
    return confirm_keyboard


def create_broadcast_progress_markup():
    """Создает клавиатуру для остановки рассылки."""
    keyboards = InlineKeyboardMarkup()
    keyboards.add(InlineKeyboardButton("❌ Остановить рассылку", callback_data="stop_broadcast"))
    return keyboards


def create_hide_message_markup(uid):
    """Создает клавиатуру для скрытия сообщения."""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("❌ Скрыть", callback_data=f"hide_message_{uid}"))
    return keyboard


def create_profile_actions_markup(user_id_to_show, block_status_str):
    """Создает клавиатуру действий для профиля пользователя в админке."""
    keyboard = InlineKeyboardMarkup(row_width=2)
    profile_url = f"tg://user?id={user_id_to_show}"
    if "Заблокирован" in block_status_str:
        block_unblock_btn = InlineKeyboardButton(
            text="🔓 Разблок",
            callback_data=f"unblock_{user_id_to_show}"
        )
    else:
        block_unblock_btn = InlineKeyboardButton(
            text="🔒 Заблок",
            callback_data=f"block_{user_id_to_show}"
        )
    add_stars_btn = InlineKeyboardButton(
        text="➕ Добавить ⭐",
        callback_data=f"add_stars_{user_id_to_show}"
    )
    subtract_stars_btn = InlineKeyboardButton(
        text="➖ Списать ⭐",
        callback_data=f"subtract_stars_{user_id_to_show}"
    )
    profile_btn = InlineKeyboardButton(text="👤 Профиль", url=profile_url)
    clickup_btn = InlineKeyboardButton(
        text="🖱️ Награда клик",
        callback_data=f"set_click_reward_for_{user_id_to_show}"
    )
    ref_reward_btn = InlineKeyboardButton(
        text="🔗 Награда реф",
        callback_data=f"set_ref_reward_for_{user_id_to_show}"
    )
    keyboard.add(block_unblock_btn)
    keyboard.add(add_stars_btn, subtract_stars_btn)
    keyboard.add(profile_btn)
    keyboard.add(clickup_btn, ref_reward_btn)
    keyboard.add(InlineKeyboardButton(text="👑 Админ-меню", callback_data="adminpanel"))
    return keyboard


def create_withdrawal_buttons(user_id, stars):
    markup = InlineKeyboardMarkup(row_width=2)
    amounts = [
        (15, "🧸", 5170233102089322756),
        (15, "💝", 5170145012310081615),
        (25, "🌹", 5168103777563050263),
        (25, "🎁", 5170250947678437525),
        (50, "🍾", 6028601630662853006),
        (50, "🚀", 5170564780938756245),
        (50, "💐", 5170314324215857265),
        (50, "🎂", 5170144170496491616),
        (100, "🏆", 5168043875654172773),
        (100, "💍", 5170690322832818290),
        (100, "💎", 5170521118301225164),
        (1700, "📱", None)  # Premium
    ]
    row_buttons = []
    for amt, emoji, star_gift_id in amounts:
        if amt == 1700:  # Обрабатываем премиум отдельно ниже
            continue
        is_available = stars >= amt
        button_text = f"{amt} ⭐️ ({emoji})" if is_available else f"{amt} ⭐️ ({emoji}) 🔒"
        # Указываем gift_id в колбэке
        button_callback = f"withdraw:{amt}:{star_gift_id}" if is_available else "insufficient_funds"
        row_buttons.append(InlineKeyboardButton(text=button_text, callback_data=button_callback))
        if len(row_buttons) == 2:
            markup.row(*row_buttons)
            row_buttons = []
    if row_buttons:  # Добавляем оставшиеся кнопки, если их нечетное количество
        markup.row(*row_buttons)

    # Кнопка Premium
    premium_amt, premium_emoji, _ = amounts[-1]
    is_premium_available = stars >= premium_amt
    prem_button_text = (
        f"Premium 6 мес. ({premium_amt}⭐️)"
        if is_premium_available
        else f"Premium 6 мес. ({premium_amt}⭐️) 🔒"
    )
    # Используем специальный маркер 'premium' вместо gift_id
    prem_button_callback = (
        f"withdraw:{premium_amt}:premium" if is_premium_available else "insufficient_funds"
    )
    markup.add(InlineKeyboardButton(text=prem_button_text, callback_data=prem_button_callback))

    markup.add(create_back_button(user_id))
    return markup


def create_admin_withdrawal_markup(user_id_req, amt, emoji, request_id, message_id=None):
    """Создает клавиатуру для админа для ОБРАБОТКИ ОДНОЙ заявки на вывод (БЕЗ кнопок ПРИНЯТЬ/ОТКЛОНИТЬ ВСЕ)."""
    inline_keyboard = InlineKeyboardMarkup(row_width=2)
    deny_callback = f"denied_req:{request_id}"  # Измененный колбэк для отказа
    paid_callback = f"paid:{user_id_req}:{amt}:{emoji}:{request_id}"  # Оставляем emoji для совместимости
    inline_keyboard.row(
        InlineKeyboardButton("✅ Отправить", callback_data=paid_callback),
        InlineKeyboardButton("🚫 Отказать", callback_data=deny_callback)
    )
    inline_keyboard.add(
        InlineKeyboardButton("👤 Профиль пользователя", url=f"tg://user?id={user_id_req}")
    )
    # УБИРАЕМ кнопки "Принять все" и "Отклонить все" отсюда
    # inline_keyboard.add(
    #     InlineKeyboardButton("✅ Принять все", callback_data="paid_all"),
    #     InlineKeyboardButton("🚫 Отклонить все", callback_data="denied_all")
    # )
    return inline_keyboard


def create_admin_task_list_markup(tasks, bot_instance):
    """Создает клавиатуру со списком заданий для админа."""
    # ... (код без изменений) ...
    keyboard = InlineKeyboardMarkup(row_width=1)
    if tasks:
        for task_info in tasks:
            try:
                # Распаковка кортежа или словаря (зависит от того, как get_tasks возвращает данные)
                if isinstance(task_info, dict):  # Если это словарь (Row объект)
                    task_id = task_info.get('id')
                    channel_id = task_info.get('channel_id')
                    reward = task_info.get('reward')
                    active = task_info.get('active')
                    task_type = task_info.get('task_type')
                    completed = task_info.get('completed_count', 0)
                    limit = task_info.get('max_completions', '?')
                else:  # Если это кортеж (старый вариант)
                    task_id, channel_id, reward, active, task_type, completed, limit = task_info[:7]

                status = "🟩 Активно" if active else "🟥 Неактивно"
                type_str = "Ссылка" if task_type == "nosub" else "Канал/Чат"
                target_str = str(channel_id)
                display_target = target_str if len(target_str) <= 25 else target_str[:22] + "..."
                button_text = f"{status} | {type_str}: {display_target} | {reward}⭐️ | {completed}/{limit} | ❌"
                delete_button = InlineKeyboardButton(
                    text=button_text, callback_data=f"delete_task_btn_{task_id}"
                )
                keyboard.add(delete_button)
            except Exception as e:
                log.error(f"Error processing task for admin list: {task_info}, error: {e}")
                task_id_str = str(task_info.get('id')) if isinstance(task_info, dict) else str(
                    task_info[0]) if task_info else '?'
                keyboard.add(
                    InlineKeyboardButton(
                        f"Ошибка задания ID: {task_id_str}",
                        callback_data="no_action"
                    )
                )
    else:
        keyboard.add(InlineKeyboardButton("Нет активных заданий", callback_data="no_action"))
    keyboard.add(InlineKeyboardButton(text="👑 Вернуться в админ-меню", callback_data="adminpanel"))
    return keyboard


def create_donate_confirmation_keyboard(user_id: int):
    """Создает клавиатуру для подтверждения доната через Stars."""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            text=f"🌟 Оплатить {DONATE_PAY} Stars",
            callback_data="donate_stars"  # Оставляем этот колбэк
        )
    )
    markup.add(create_back_button(user_id))
    return markup
