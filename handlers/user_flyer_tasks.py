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




async def ensure_flyer_table():
    pool = database.db_pool
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS flyer_completed (
                user_id BIGINT NOT NULL,
                signature TEXT NOT NULL,
                completed_at TIMESTAMP DEFAULT NOW(),
                reward REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, signature)
            )
        """)


async def is_flyer_task_done(user_id: int, signature: str) -> bool:
    pool = database.db_pool
    if not pool:
        return False
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM flyer_completed WHERE user_id=$1 AND signature=$2",
            user_id, signature
        )
        return row is not None


async def mark_flyer_task_done(user_id: int, signature: str, reward: float):
    pool = database.db_pool
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO flyer_completed (user_id, signature, reward) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            user_id, signature, reward
        )

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
        await call.message.answer("\u26a0\ufe0f \u0417\u0430\u0434\u0430\u043d\u0438\u044f \u0441\u043f\u043e\u043d\u0441\u043e\u0440\u043e\u0432 \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b.", reply_markup=back_markup)
        return

    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        pass

    tasks = await flyer_get_tasks(user_id, language_code)

    if tasks is None:
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        await call.message.answer("\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438 \u0437\u0430\u0434\u0430\u043d\u0438\u0439. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u043e\u0437\u0436\u0435.", reply_markup=back_markup)
        return

    if not tasks:
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        await call.message.answer("\u2705 \u0412\u0441\u0435 \u0437\u0430\u0434\u0430\u043d\u0438\u044f \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u044b! \u041d\u043e\u0432\u044b\u0435 \u043f\u043e\u044f\u0432\u044f\u0442\u0441\u044f \u043f\u043e\u0437\u0436\u0435.", reply_markup=back_markup)
        return

    await ensure_flyer_table()
    multiplier = await get_flyer_reward_multiplier()
    markup = InlineKeyboardMarkup(row_width=1)
    total_reward = 0.0

    # Filter out already completed tasks
    pending_tasks = []
    for task in tasks:
        sig = task.get("signature", "")
        if sig and await is_flyer_task_done(user_id, sig):
            continue
        pending_tasks.append(task)

    if not pending_tasks:
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        await call.message.answer("\u2705 \u0412\u0441\u0435 \u0437\u0430\u0434\u0430\u043d\u0438\u044f \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u044b! \u041d\u043e\u0432\u044b\u0435 \u043f\u043e\u044f\u0432\u044f\u0442\u0441\u044f \u043f\u043e\u0437\u0436\u0435.", reply_markup=back_markup)
        return

    for task in pending_tasks:
        name = task.get("name", "Zadanie")
        task_type = task.get("task", "")
        price = task.get("price", 0)
        links = task.get("links", [])
        reward = round(price * multiplier, 2)
        total_reward += reward

        type_emoji = "\U0001f4e2" if "channel" in task_type else "\U0001f916"

        if links:
            markup.add(InlineKeyboardButton(f"{type_emoji} {name[:40]}", url=links[0]))

    text = (
        "\U0001f4cb <b>\u0417\u0430\u0434\u0430\u043d\u0438\u044f \u0441\u043f\u043e\u043d\u0441\u043e\u0440\u043e\u0432</b>\n\n"
        "\u0412\u044b\u043f\u043e\u043b\u043d\u0438 \u0432\u0441\u0435 \u0437\u0430\u0434\u0430\u043d\u0438\u044f \u0432\u044b\u0448\u0435 \u0438 \u043d\u0430\u0436\u043c\u0438 \u043a\u043d\u043e\u043f\u043a\u0443 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438.\n"
        f"\U0001f4b0 <b>\u041d\u0430\u0433\u0440\u0430\u0434\u0430: {total_reward:.2f} \u2b50</b>"
    )

    markup.add(InlineKeyboardButton("\u2705 \u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0432\u0441\u0435", callback_data="flycheck_all"))
    markup.add(create_back_button(user_id))
    await call.message.answer(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)


async def handle_flyer_check_all(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    language_code = call.from_user.language_code or "ru"

    try:
        await call.answer("\U0001f504 \u041f\u0440\u043e\u0432\u0435\u0440\u044f\u044e...")
    except (InvalidQueryID, Exception):
        pass

    tasks = await flyer_get_tasks(user_id, language_code)
    if not tasks:
        try:
            await call.answer("\u2705 \u0417\u0430\u0434\u0430\u043d\u0438\u0439 \u043d\u0435\u0442!", show_alert=True)
        except (InvalidQueryID, Exception):
            pass
        return

    multiplier = await get_flyer_reward_multiplier()
    completed_count = 0
    total_reward = 0.0
    not_done = []
    not_done_tasks = []

    await ensure_flyer_table()
    for task in tasks:
        signature = task.get("signature", "")
        if not signature:
            continue
        # Skip already rewarded tasks
        if await is_flyer_task_done(user_id, signature):
            continue
        result = await flyer_check_task(signature)
        result_lower = result.lower() if isinstance(result, str) else ""

        if result_lower in ("subscribed", "completed", "complete", "done", "true", "success", "started"):
            price = task.get("price", 1.0)
            reward = round(price * multiplier, 2)
            try:
                await database.add_stars(user_id, reward)
                await mark_flyer_task_done(user_id, signature, reward)
                completed_count += 1
                total_reward += reward
                log.info(f"User {user_id} completed flyer task {signature}. Reward: {reward}")
            except Exception as e:
                log.exception(f"Error adding stars for flyer task: {e}")
        else:
            not_done.append(task.get("name", "?"))
            not_done_tasks.append(task)

    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        pass

    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        pass

    if completed_count > 0 and not not_done:
        await call.message.answer(
            f"\u2705 \u0412\u0441\u0435 \u0437\u0430\u0434\u0430\u043d\u0438\u044f \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u044b!\n\U0001f4b0 \u041d\u0430\u0433\u0440\u0430\u0434\u0430: +{total_reward:.2f} \u2b50",
            reply_markup=InlineKeyboardMarkup().add(create_back_button(user_id))
        )
    else:
        # Show remaining incomplete tasks as buttons
        markup = InlineKeyboardMarkup(row_width=1)
        for nd_task in not_done_tasks:
            nd_name = nd_task.get("name", "?")
            nd_links = nd_task.get("links", [])
            nd_type = nd_task.get("task", "")
            nd_emoji = "\U0001f4e2" if "channel" in nd_type else "\U0001f916"
            if nd_links:
                markup.add(InlineKeyboardButton(f"{nd_emoji} {nd_name[:40]}", url=nd_links[0]))
        
        text = ""
        if completed_count > 0:
            text += f"\u2705 \u0412\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u043e: {completed_count} | +{total_reward:.2f} \u2b50\n\n"
        text += "\u274c \u041e\u0441\u0442\u0430\u043b\u0438\u0441\u044c \u043d\u0435\u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d\u043d\u044b\u0435 \u0437\u0430\u0434\u0430\u043d\u0438\u044f:"
        
        markup.add(InlineKeyboardButton("\u2705 \u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u0441\u043d\u043e\u0432\u0430", callback_data="flycheck_all"))
        markup.add(create_back_button(user_id))
        await call.message.answer(text, reply_markup=markup, disable_web_page_preview=True)


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
    markup.add(InlineKeyboardButton("\u274c \u041e\u0442\u043c\u0435\u043d\u0430", callback_data="adminpanel"))
    current = await get_flyer_reward_multiplier()
    await call.message.edit_text(
        f"\u2699\ufe0f <b>\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 \u043d\u0430\u0433\u0440\u0430\u0434\u044b FlyerBot</b>\n\n"
        f"\u0422\u0435\u043a\u0443\u0449\u0438\u0439 \u043c\u043d\u043e\u0436\u0438\u0442\u0435\u043b\u044c: <b>{current}x</b>\n"
        f"(FlyerBot \u0434\u0430\u0451\u0442 \u0446\u0435\u043d\u0443 \u0437\u0430 \u0437\u0430\u0434\u0430\u043d\u0438\u0435, \u043c\u043d\u043e\u0436\u0438\u0442\u0435\u043b\u044c \u0443\u043c\u043d\u043e\u0436\u0430\u0435\u0442 \u0435\u0451)\n\n"
        f"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043d\u043e\u0432\u044b\u0439 \u043c\u043d\u043e\u0436\u0438\u0442\u0435\u043b\u044c:",
        reply_markup=markup, parse_mode="HTML"
    )


async def admin_set_flyer_mult_value(call: CallbackQuery, bot: Bot):
    from settings import ADMIN_IDS
    if call.from_user.id not in ADMIN_IDS:
        return
    try:
        mult = float(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("\u041e\u0448\u0438\u0431\u043a\u0430", show_alert=True)
        return
    await database.set_config_value("flyer_reward_multiplier", str(mult))
    await call.answer(f"\u2705 \u041c\u043d\u043e\u0436\u0438\u0442\u0435\u043b\u044c \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d: {mult}x", show_alert=True)
    await admin_set_flyer_reward(call, bot)


def register_user_flyer_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(
        lambda call: show_flyer_tasks(call, bot),
        lambda c: c.data == "flyer_tasks", state="*"
    )
    dp.register_callback_query_handler(
        lambda call: handle_flyer_check_all(call, bot),
        lambda c: c.data == "flycheck_all", state="*"
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
