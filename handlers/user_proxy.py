# handlers/user_proxy.py — Покупка прокси за звёзды (async/PG)
import logging

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.exceptions import (
    MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID, MessageNotModified
)

from database import (
    get_available_proxies, buy_proxy, get_user, get_users_balance,
    get_user_purchased_proxies, is_user_blocked, get_proxy_by_id
)
from keyboards import create_back_button
from handlers.common import check_subscription

log = logging.getLogger('handlers.user_proxy')


async def show_proxy_shop(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:
        await call.answer()
    except InvalidQueryID:
        return
    except Exception:
        return

    if await is_user_blocked(user_id):
        await bot.send_message(user_id, "❌ Вы заблокированы.")
        return

    if not await check_subscription(bot, user_id, chat_id):
        from utils import t
        await bot.send_message(user_id, t(user_id, "not_subscribed"))
        return

    proxies = await get_available_proxies()
    balance = await get_users_balance(user_id)

    if not proxies:
        text = (
            "🌐 <b>Магазин прокси</b>\n\n"
            "😔 Сейчас нет доступных прокси.\nЗагляни позже!"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📦 Мои покупки", callback_data="my_proxies"))
        markup.add(create_back_button(user_id))
        try:
            await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        return

    types_available = {}
    for p in proxies:
        ptype = p['proxy_type']
        if ptype not in types_available:
            types_available[ptype] = []
        types_available[ptype].append(p)

    text = (
        f"🌐 <b>Магазин прокси</b>\n\n"
        f"💰 Твой баланс: <code>{balance:.2f}⭐</code>\n\n"
        f"Доступно прокси: <b>{len(proxies)}</b>\n\n"
    )

    for ptype, items in types_available.items():
        min_price = min(p['price'] for p in items)
        max_price = max(p['price'] for p in items)
        price_range = f"{min_price:.1f}" if min_price == max_price else f"{min_price:.1f}–{max_price:.1f}"
        text += f"🔹 <b>{ptype}</b> — {len(items)} шт. ({price_range}⭐)\n"

    text += "\n<i>Выбери прокси для покупки:</i>"

    markup = InlineKeyboardMarkup(row_width=1)
    for p in proxies[:15]:
        can_buy = balance >= p['price']
        emoji = "✅" if can_buy else "🔒"
        btn_text = f"{emoji} {p['proxy_type']} | {p['price']:.1f}⭐"
        callback = f"buy_proxy:{p['id']}" if can_buy else "proxy_no_funds"
        markup.add(InlineKeyboardButton(btn_text, callback_data=callback))

    markup.add(InlineKeyboardButton("📦 Мои покупки", callback_data="my_proxies"))
    markup.add(create_back_button(user_id))

    try:
        await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        try:
            await call.message.delete()
        except:
            pass
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")


async def handle_buy_proxy(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        return

    try:
        proxy_id = int(call.data.split(":")[1])
    except (ValueError, IndexError):
        return

    proxy = await get_proxy_by_id(proxy_id)
    if not proxy or proxy['is_sold']:
        await bot.send_message(
            call.message.chat.id, "❌ Этот прокси уже продан или не существует.",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🌐 В магазин", callback_data="proxy_shop")
            )
        )
        return

    text = (
        f"🛒 <b>Подтверждение покупки</b>\n\n"
        f"🔹 Тип: <b>{proxy['proxy_type']}</b>\n"
        f"💰 Цена: <b>{proxy['price']:.2f}⭐</b>\n\n"
        f"Подтвердить?"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Купить", callback_data=f"confirm_buy_proxy:{proxy_id}"),
        InlineKeyboardButton("❌ Отмена", callback_data="proxy_shop")
    )

    try:
        await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")


async def confirm_buy_proxy(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    try:
        await call.answer()
    except InvalidQueryID:
        return

    try:
        proxy_id = int(call.data.split(":")[1])
    except (ValueError, IndexError):
        return

    success, message, address = await buy_proxy(user_id, proxy_id)

    if success:
        proxy_data = await get_proxy_by_id(proxy_id)
        proxy_type = proxy_data['proxy_type'] if proxy_data else "N/A"
        result_text = (
            f"✅ <b>Покупка успешна!</b>\n\n"
            f"🌐 Тип: <b>{proxy_type}</b>\n\n"
            f"⚠️ Нажми кнопку ниже, чтобы подключить прокси:"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔗 Подключить прокси", url=address))
        markup.add(InlineKeyboardButton("🌐 В магазин", callback_data="proxy_shop"))
        markup.add(create_back_button(user_id))
    else:
        result_text = message
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌐 В магазин", callback_data="proxy_shop"))
        markup.add(create_back_button(user_id))

    try:
        await call.message.edit_text(result_text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await bot.send_message(chat_id, result_text, reply_markup=markup, parse_mode="HTML")


async def proxy_no_funds(call: CallbackQuery, bot: Bot):
    try:
        await call.answer("❌ Недостаточно звёзд для покупки!", show_alert=True)
    except Exception:
        pass


async def show_my_proxies(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        return

    purchases = await get_user_purchased_proxies(user_id)

    if not purchases:
        text = "📦 <b>Мои прокси</b>\n\n😔 У тебя пока нет купленных прокси."
    else:
        text = f"📦 <b>Мои прокси ({len(purchases)})</b>\n\n"
        for p in purchases[:20]:
            purchased_at = p['purchased_at'].strftime('%Y-%m-%d %H:%M') if p['purchased_at'] else ''
            text += (
                f"🔹 <b>{p['proxy_type']}</b> | {p['price']:.1f}⭐\n"
                f"   <code>{p['address']}</code>\n"
                f"   📅 {purchased_at}\n\n"
            )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🌐 В магазин", callback_data="proxy_shop"))
    markup.add(create_back_button(user_id))

    try:
        await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")


def register_user_proxy_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(
        lambda call: show_proxy_shop(call, bot), lambda c: c.data == "proxy_shop", state="*"
    )
    dp.register_callback_query_handler(
        lambda call: handle_buy_proxy(call, bot), lambda c: c.data.startswith("buy_proxy:"), state="*"
    )
    dp.register_callback_query_handler(
        lambda call: confirm_buy_proxy(call, bot), lambda c: c.data.startswith("confirm_buy_proxy:"), state="*"
    )
    dp.register_callback_query_handler(
        lambda call: proxy_no_funds(call, bot), lambda c: c.data == "proxy_no_funds", state="*"
    )
    dp.register_callback_query_handler(
        lambda call: show_my_proxies(call, bot), lambda c: c.data == "my_proxies", state="*"
    )
    log.info("User proxy handlers registered.")
