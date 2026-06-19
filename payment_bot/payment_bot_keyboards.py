from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import payment_bot_settings as p_settings


def get_main_payment_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💳 Пополнить баланс (Stars)", callback_data="top_up_balance")],
        [InlineKeyboardButton(text="🚀 Купить буст (Stars)", callback_data="buy_boost_menu")],
        [InlineKeyboardButton(text="⬅️ В основного бота", url=f"https://t.me/{p_settings.MAIN_BOT_USERNAME}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_boost_selection_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for boost_id, boost_info in p_settings.BOOST_OPTIONS.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{boost_info['name']} ({boost_info['price_stars']} ⭐)",
                callback_data=f"confirm_boost_purchase:{boost_id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_payment_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_to_main_payment_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="⬅️ В меню платежей", callback_data="back_to_payment_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)



def get_topup_amount_keyboard() -> InlineKeyboardMarkup:
    preset_amounts = [100, 250, 500, 1000]
    buttons = []
    row = []
    for amount in preset_amounts:
        row.append(InlineKeyboardButton(text=f"{amount} ⭐", callback_data=f"topup_preset:{amount}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="Другая сумма ✍️", callback_data="topup_manual_amount")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_payment_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

