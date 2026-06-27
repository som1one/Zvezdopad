# handlers/admin_proxy.py — Управление прокси-магазином (async/PG)
import logging

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified

from database import (
    add_proxy, get_all_proxies, delete_proxy, get_proxy_stats, get_proxy_by_id
)
from settings import ADMIN_IDS
from keyboards import create_admin_cancel_markup
from states import AdminAddProxyState

log = logging.getLogger('handlers.admin_proxy')


async def show_proxy_admin_menu(call: CallbackQuery, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        return
    await call.answer()

    stats = await get_proxy_stats()

    text = (
        f"🌐 <b>Управление прокси-магазином</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"  ▫️ Всего прокси: <code>{stats['total']}</code>\n"
        f"  ▫️ Доступно: <code>{stats['available']}</code>\n"
        f"  ▫️ Продано: <code>{stats['sold']}</code>\n"
        f"  ▫️ Выручка: <code>{stats['revenue']:.2f}⭐</code>\n"
    )

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("➕ Добавить прокси", callback_data="admin_proxy_add"),
        InlineKeyboardButton("📋 Список доступных", callback_data="admin_proxy_list"),
        InlineKeyboardButton("📋 Все прокси (вкл. проданные)", callback_data="admin_proxy_list_all"),
        InlineKeyboardButton("👑 Админ-меню", callback_data="adminpanel")
    )

    try:
        await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except MessageNotModified:
        pass
    except Exception:
        await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")


async def start_add_proxy(call: CallbackQuery, state: FSMContext):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        return
    await call.answer()

    text = (
        "➕ <b>Добавление прокси</b>\n\n"
        "Отправьте данные прокси в формате:\n"
        "<code>тип|адрес|цена</code>\n\n"
        "📌 <b>Примеры:</b>\n"
        "<code>SOCKS5|login:pass@ip:port|50</code>\n"
        "<code>HTTP|ip:port:login:pass|30</code>\n\n"
        "Можно несколько прокси за раз (каждый с новой строки)."
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Отмена", callback_data="admin_proxy_menu"))

    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await AdminAddProxyState.waiting_for_proxy_data.set()


async def process_add_proxy(message: types.Message, state: FSMContext, bot: Bot):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS:
        await state.finish()
        return

    lines = message.text.strip().split('\n')
    added_count = 0
    errors = []

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split('|')
        if len(parts) != 3:
            errors.append(f"Строка {i}: неверный формат (нужно тип|адрес|цена)")
            continue

        proxy_type = parts[0].strip().upper()
        address = parts[1].strip()
        price_str = parts[2].strip()

        if proxy_type not in ('HTTP', 'HTTPS', 'SOCKS4', 'SOCKS5'):
            errors.append(f"Строка {i}: неверный тип '{proxy_type}'")
            continue

        try:
            price = float(price_str)
            if price <= 0:
                raise ValueError()
        except ValueError:
            errors.append(f"Строка {i}: неверная цена '{price_str}'")
            continue

        try:
            await add_proxy(proxy_type, address, price)
            added_count += 1
        except Exception as e:
            errors.append(f"Строка {i}: ошибка БД — {e}")

    await state.finish()

    result_text = f"✅ Добавлено прокси: <b>{added_count}</b>"
    if errors:
        result_text += f"\n\n⚠️ Ошибки ({len(errors)}):\n" + "\n".join(errors[:10])

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🌐 Прокси-меню", callback_data="admin_proxy_menu"))
    markup.add(InlineKeyboardButton("👑 Админ-меню", callback_data="adminpanel"))

    await message.answer(result_text, reply_markup=markup, parse_mode="HTML")


async def show_proxy_list(call: CallbackQuery, bot: Bot, include_sold: bool = False):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        return
    await call.answer()

    proxies = await get_all_proxies(include_sold=include_sold)

    if not proxies:
        text = "📋 Список прокси пуст."
    else:
        lines = ["📋 <b>Прокси в магазине:</b>\n"]
        for p in proxies[:30]:
            status = "🟢" if not p.get('is_sold') else "🔴"
            sold_info = ""
            if p.get('is_sold') and p.get('sold_to'):
                sold_info = f" → 👤{p['sold_to']}"
            lines.append(
                f"{status} <code>#{p['id']}</code> | {p['proxy_type']} | "
                f"{p['price']:.1f}⭐{sold_info}"
            )
        if len(proxies) > 30:
            lines.append(f"\n... и ещё {len(proxies) - 30}")
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🗑 Удалить прокси по ID", callback_data="admin_proxy_delete_prompt"))
    markup.add(InlineKeyboardButton("🌐 Прокси-меню", callback_data="admin_proxy_menu"))
    markup.add(InlineKeyboardButton("👑 Админ-меню", callback_data="adminpanel"))

    try:
        await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except MessageNotModified:
        pass
    except Exception:
        await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")


async def show_proxy_list_available(call: CallbackQuery, bot: Bot):
    await show_proxy_list(call, bot, include_sold=False)


async def show_proxy_list_all(call: CallbackQuery, bot: Bot):
    await show_proxy_list(call, bot, include_sold=True)


async def proxy_delete_prompt(call: CallbackQuery, state: FSMContext):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        return
    await call.answer()

    text = (
        "🗑 <b>Удаление прокси</b>\n\n"
        "Отправьте ID прокси для удаления (число).\n"
        "Можно несколько через пробел: <code>1 5 12</code>"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ Отмена", callback_data="admin_proxy_menu"))

    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await state.set_state("admin_proxy_delete")


async def process_proxy_delete(message: types.Message, state: FSMContext, bot: Bot):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS:
        await state.finish()
        return

    ids_str = message.text.strip().split()
    deleted = 0
    not_found = []

    for id_str in ids_str:
        try:
            proxy_id = int(id_str)
            if await delete_proxy(proxy_id):
                deleted += 1
            else:
                not_found.append(str(proxy_id))
        except ValueError:
            not_found.append(id_str)

    await state.finish()

    text = f"✅ Удалено: <b>{deleted}</b>"
    if not_found:
        text += f"\n⚠️ Не найдены/уже проданы: {', '.join(not_found)}"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🌐 Прокси-меню", callback_data="admin_proxy_menu"))

    await message.answer(text, reply_markup=markup, parse_mode="HTML")


def register_admin_proxy_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(
        lambda call: show_proxy_admin_menu(call, bot),
        lambda c: c.data == "admin_proxy_menu", state="*"
    )
    dp.register_callback_query_handler(
        start_add_proxy,
        lambda c: c.data == "admin_proxy_add", state="*"
    )
    dp.register_message_handler(
        lambda msg, state: process_add_proxy(msg, state, bot),
        state=AdminAddProxyState.waiting_for_proxy_data
    )
    dp.register_callback_query_handler(
        lambda call: show_proxy_list_available(call, bot),
        lambda c: c.data == "admin_proxy_list", state="*"
    )
    dp.register_callback_query_handler(
        lambda call: show_proxy_list_all(call, bot),
        lambda c: c.data == "admin_proxy_list_all", state="*"
    )
    dp.register_callback_query_handler(
        proxy_delete_prompt,
        lambda c: c.data == "admin_proxy_delete_prompt", state="*"
    )
    dp.register_message_handler(
        lambda msg, state: process_proxy_delete(msg, state, bot),
        state="admin_proxy_delete"
    )
    log.info("Admin proxy handlers registered.")
