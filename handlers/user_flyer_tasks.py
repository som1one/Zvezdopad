import logging
import aiohttp

from aiogram import Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID

import database
from settings import FLYER_API_KEY
from utils import t
from keyboards import create_back_button
from handlers.common import check_subscription

log = logging.getLogger('handlers.user_flyer_tasks')

FLYER_API_URL = "https://api.flyerhubs.com"


async def flyer_get_tasks(user_id: int, language_code: str = "ru", limit: int = 5) -> list | None:
    if not FLYER_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"key": FLYER_API_KEY, "user_id": user_id, "language_code": language_code, "limit": limit}
            async with session.post(f"{FLYER_API_URL}/get_tasks", json=payload) as resp:
                data = await resp.json()
                if data.get("error"):
                    log.error(f"FlyerBot get_tasks error for {user_id}: {data['error']}")
                    return None
                return data.get("result", [])
    except Exception as e:
        log.exception(f"FlyerBot get_tasks exception for {user_id}: {e}")
        return None


async def flyer_check_task(signature: str) -> str | None:
    if not FLYER_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"key": FLYER_API_KEY, "signature": signature}
            async with session.post(f"{FLYER_API_URL}/check_task", json=payload) as resp:
                data = await resp.json()
                if data.get("error"):
                    log.warning(f"FlyerBot check_task error: {data['error']}")
                    return data.get("error")
                return data.get("result")
    except Exception as e:
        log.exception(f"FlyerBot check_task exception: {e}")
        return None


async def get_flyer_reward_multiplier() -> float:
    try:
        val = await database.get_config_value("flyer_reward_multiplier", "1.0")
        return float(val)
    except:
        return 1.0


async def show_flyer_tasks(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    language_code = call.from_user.language_code or "ru"

    try:
        await call.answer()
    except (InvalidQueryID, Exception):
        pass

    if not await check_subscription(bot, user_id, chat_id):
        try:
            await call.answer(t(user_id, "not_subscribed"), show_alert=True)
        except (InvalidQueryID, Exception):
            pass
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        return

    if not FLYER_API_KEY:
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        await call.message.answer("⚠️ Задания спонсоров временно недоступны.", reply_markup=back_markup)
        return

    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        pass

    tasks = await flyer_get_tasks(user_id, language_code)

    if tasks is None:
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        await call.message.answer("❌ Ошибка загрузки заданий. Попробуйте позже.", reply_markup=back_markup)
        return

    if not tasks:
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        await call.message.answer("✅ Все задания выполнены! Новые появятся позже.", reply_markup=back_markup)
        return

    multiplier = await get_flyer_reward_multiplier()
    markup = InlineKeyboardMarkup(row_width=1)
    text = "📋 <b>Задания спонсоров</b>\n\n"

    for i, task in enumerate(tasks):
        name = task.get("name", f"Задание #{i+1}")
        task_type = task.get("task", "")
        price = task.get("price", 0)
        links = task.get("links", [])
        signature = task.get("signature", "")
        reward = round(price * multiplier, 2)

        type_emoji = "📢" if "channel" in task_type else "🤖"
        type_text = "Подписаться" if "channel" in task_type else "Запустить бота"

        text += f"{type_emoji} <b>{name}</b>\n   └ {type_text} — <b>{reward}⭐</b>\n\n"

        if links:
            markup.add(InlineKeyboardButton(f"{type_emoji} {name[:35]}", url=links[0]))

        if signature:
            markup.add(InlineKeyboardButton(f"✅ Проверить: {name[:25]}", callback_data=f"flycheck:{signature}"))

    markup.add(create_back_button(user_id))
    await call.message.answer(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)


async def handle_flyer_check(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    signature = call.data.replace("flycheck:", "")

    try:
        await call.answer("🔄 Проверяю...")
    except (InvalidQueryID, Exception):
        pass

    result = await flyer_check_task(signature)

    if not result:
        try:
            await call.answer("❌ Ошибка проверки. Попробуйте позже.", show_alert=True)
        except (InvalidQueryID, Exception):
            pass
        return

    result_lower = result.lower() if isinstance(result, str) else ""

    if result_lower in ("subscribed", "completed", "complete", "done", "true", "success", "started"):
        tasks = await flyer_get_tasks(user_id)
        price = 1.0
        if tasks:
            for task in tasks:
                if task.get("signature") == signature:
                    price = task.get("price", 1.0)
                    break

        multiplier = await get_flyer_reward_multiplier()
        reward = round(price * multiplier, 2)

        try:
            await database.add_stars(user_id, reward)
            log.info(f"User {user_id} completed flyer task {signature}. Reward: {reward}")
        except Exception as e:
            log.exception(f"Error adding stars for flyer task: {e}")

        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass

        await call.message.answer(f"✅ Задание выполнено! +{reward:.2f} ⭐")
        await show_flyer_tasks(call, bot)

    elif result_lower in ("not_subscribed", "not_completed", "false", "pending", "incomplete"):
        try:
            await call.answer("❌ Задание не выполнено! Подпишитесь/запустите и попробуйте снова.", show_alert=True)
        except (InvalidQueryID, Exception):
            pass
    else:
        try:
            await call.answer(f"⚠️ Результат: {result}", show_alert=True)
        except (InvalidQueryID, Exception):
            pass


async def admin_set_flyer_reward(call: CallbackQuery, bot: Bot):
    from settings import ADMIN_IDS
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("0.5x", callback_data="flyer_mult:0.5"),
        InlineKeyboardButton("1.0x", callback_data="flyer_mult:1.0"),
        InlineKeyboardButton("1.5x", callback_data="flyer_mult:1.5"),
    )
    markup.add(
        InlineKeyboardButton("2.0x", callback_data="flyer_mult:2.0"),
        InlineKeyboardButton("3.0x", callback_data="flyer_mult:3.0"),
        InlineKeyboardButton("5.0x", callback_data="flyer_mult:5.0"),
    )
    markup.add(InlineKeyboardButton("❌ Отмена", callback_data="adminpanel"))
    current = await get_flyer_reward_multiplier()
    await call.message.edit_text(
        f"⚙️ <b>Настройка награды FlyerBot</b>\n\n"
        f"Текущий множитель: <b>{current}x</b>\n"
        f"(FlyerBot даёт цену за задание, множитель умножает её)\n\n"
        f"Выберите новый множитель:",
        reply_markup=markup, parse_mode="HTML"
    )


async def admin_set_flyer_mult_value(call: CallbackQuery, bot: Bot):
    from settings import ADMIN_IDS
    if call.from_user.id not in ADMIN_IDS:
        return
    try:
        mult = float(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Ошибка", show_alert=True)
        return
    await database.set_config_value("flyer_reward_multiplier", str(mult))
    await call.answer(f"✅ Множитель установлен: {mult}x", show_alert=True)
    await admin_set_flyer_reward(call, bot)


def register_user_flyer_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(
        lambda call: show_flyer_tasks(call, bot),
        lambda c: c.data == "flyer_tasks", state="*"
    )
    dp.register_callback_query_handler(
        lambda call: handle_flyer_check(call, bot),
        lambda c: c.data.startswith("flycheck:"), state="*"
    )
    dp.register_callback_query_handler(
        lambda call: admin_set_flyer_reward(call, bot),
        lambda c: c.data == "admin_flyer_reward", state="*"
    )
    dp.register_callback_query_handler(
        lambda call: admin_set_flyer_mult_value(call, bot),
        lambda c: c.data.startswith("flyer_mult:"), state="*"
    )
    log.info("User FlyerBot task handlers registered.")
