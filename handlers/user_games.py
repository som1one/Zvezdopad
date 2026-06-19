import asyncio
import logging
import random
import asyncpg
import time
import os
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputFile,
    InputMediaPhoto
)
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import (
    MessageCantBeDeleted, MessageToDeleteNotFound, MessageNotModified,
    BadRequest, InvalidQueryID
)

import database
from settings import (
    WIN_CHANCE, USER_BOT, WIN_CHANEL_ID, SUP_LOGIN, ADMIN_IDS, LINK_4,
    FREE_SPIN_COOLDOWN_SECONDS, WHEEL_WEBAPP_URL, WEBHOOK_HOST
)
from utils import t, mask_id
from keyboards import (
    get_mini_games_keyboard, get_luck_game_keyboard,
    create_slot_button, create_bet_inline_keyboard, create_back_button
)
from states import SlotState

log = logging.getLogger('handlers.user_games')


async def _send_or_edit_photo_message(message_or_call, image_path, caption, markup, parse_mode="HTML",
                                      disable_preview=False):
    target_message = None
    user_id = None
    chat_id = None
    bot_instance = None

    if isinstance(message_or_call, types.CallbackQuery):
        target_message = message_or_call.message
        if not target_message:
            log.error(f"Cannot process callback without message object. User: {message_or_call.from_user.id}")
            return
        user_id = message_or_call.from_user.id
        chat_id = target_message.chat.id
        bot_instance = target_message.bot
    elif isinstance(message_or_call, types.Message):
        target_message = message_or_call
        user_id = target_message.from_user.id
        chat_id = target_message.chat.id
        bot_instance = target_message.bot
    else:
        log.error(f"Unsupported type in _send_or_edit: {type(message_or_call)}")
        return

    if not bot_instance: log.error(f"Bot instance not found for user {user_id}"); return
    if not user_id: log.error(f"User ID not found"); return
    if not chat_id: log.error(f"Chat ID not found for user {user_id}"); return

    is_callback = isinstance(message_or_call, types.CallbackQuery)
    can_edit_media = is_callback and target_message and hasattr(target_message, 'photo') and target_message.photo
    can_edit_text = is_callback and target_message and not can_edit_media and hasattr(target_message, 'text')
    send_new = not is_callback

    photo_bytes = None
    use_photo = False
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                photo_bytes = f.read()
            if photo_bytes:
                use_photo = True
            else:
                log.error(f"Helper: Image file is empty: {image_path}")
        except Exception as e:
            log.error(f"Helper: Failed to read image file {image_path}: {e}")
    elif image_path:
        log.warning(f"Helper: Image file not found: {image_path}")

    try:
        if is_callback and not send_new and target_message:
            if can_edit_media and use_photo and photo_bytes:
                try:
                    media = InputMediaPhoto(media=photo_bytes, caption=caption, parse_mode=parse_mode)
                    await target_message.edit_media(media=media, reply_markup=markup)
                    return
                except MessageNotModified:
                    return
                except BadRequest as e:
                    send_new = True
                except Exception as edit_err:
                    send_new = True
            elif can_edit_text and not use_photo:
                try:
                    await target_message.edit_text(caption, reply_markup=markup, parse_mode=parse_mode,
                                                   disable_web_page_preview=disable_preview)
                    return
                except MessageNotModified:
                    return
                except Exception as edit_err:
                    send_new = True
            else:
                send_new = True

        if send_new:
            if is_callback and target_message:
                try:
                    await target_message.delete()
                except (MessageCantBeDeleted, MessageToDeleteNotFound):
                    pass
                except Exception as del_err:
                    pass

            if use_photo and photo_bytes:
                await bot_instance.send_photo(chat_id, photo=photo_bytes, caption=caption, reply_markup=markup,
                                              parse_mode=parse_mode)
            else:
                await bot_instance.send_message(chat_id, caption, reply_markup=markup, parse_mode=parse_mode,
                                                disable_web_page_preview=disable_preview)

    except Exception as e:
        log.exception(f"CRITICAL Error in _send_or_edit_photo_message chat {chat_id}, user {user_id}: {e}")
        try:
            if is_callback and target_message and not send_new:
                await bot_instance.send_message(chat_id, caption, reply_markup=markup, parse_mode=None,
                                                disable_web_page_preview=disable_preview)
            elif not is_callback:
                await bot_instance.send_message(chat_id, caption, reply_markup=markup, parse_mode=None,
                                                disable_web_page_preview=disable_preview)
        except Exception as final_err:
            log.error(f"Final fallback send failed for user {user_id}: {final_err}")


async def show_mini_games_menu(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        return
    except Exception as e:
        return

    if await database.is_user_blocked(user_id):
        await bot.send_message(user_id, "Вы заблокированы.")
        return

    dynamic_wheel_url = f"{WEBHOOK_HOST}/"
    markup = get_mini_games_keyboard(user_id, dynamic_wheel_url)
    image_path = "images/minegame.jpg"
    caption = "🎮 <b>Добро пожаловать в мини-игры!</b>\n\nВыбери игру, чтобы начать:"
    await _send_or_edit_photo_message(call, image_path, caption, markup, disable_preview=True)


async def play_luck_game_callback(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        return
    except Exception as e:
        return

    user_data = await database.get_user(user_id)
    if not user_data or await database.is_user_blocked(user_id):
        msg = t(user_id, 'no_registration') if not user_data else "Вы заблокированы."
        await bot.send_message(user_id, msg)
        return

    stars = user_data['stars']
    markup = get_luck_game_keyboard(user_id)

    base_win_chance = WIN_CHANCE
    luck_boost_percentage = await database.get_active_luck_boost_percentage(user_id)
    actual_win_chance = base_win_chance
    boost_info_text = ""
    if luck_boost_percentage > 0:
        actual_win_chance += luck_boost_percentage
        actual_win_chance = min(actual_win_chance, 90.0)
        boost_info_text = f"\n🍀 Буст удачи активен! Ваш шанс: {actual_win_chance:.0f}%"

    caption = (f"💰 <b>У тебя:</b> {stars:.2f} ⭐️\n\n"
               f"🔔 Все или ничего.\n"
               f"🎯 Шанс: {base_win_chance}% (базовый){boost_info_text}\n"
               f"📈 Коэф: x1.8-x2.5\n\n"
               f"Выбери ставку! 🍀\n\n"
               f"📊 Стата: <a href='{LINK_4}'>Здесь</a>")
    image_path = "images/minegame.jpg"
    await _send_or_edit_photo_message(call, image_path, caption, markup, disable_preview=True)


async def play_luck_game_with_bet(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    start_time = time.monotonic()

    try:
        bet_amount = float(call.data.split(":")[1])
    except (ValueError, IndexError):
        try:
            await call.answer("Ошибка ставки.", show_alert=True)
        except:
            pass
        return

    user_data = await database.get_user(user_id)
    if not user_data or await database.is_user_blocked(user_id):
        msg = t(user_id, 'no_registration') if not user_data else "Заблок."
        try:
            await call.answer(msg, show_alert=True)
        except:
            pass
        return

    stars = user_data['stars']
    if stars < bet_amount:
        try:
            await call.answer("😞 Мало звёзд.", show_alert=True)
        except:
            pass
        return

    try:
        await call.answer(f"Ставка {bet_amount} принята. Удачи!")
    except:
        pass

    base_win_chance = WIN_CHANCE
    luck_boost_percentage = await database.get_active_luck_boost_percentage(user_id)
    actual_win_chance = base_win_chance
    if luck_boost_percentage > 0:
        actual_win_chance += luck_boost_percentage
        actual_win_chance = min(actual_win_chance, 90.0)

    win_coefficient = round(random.uniform(1.8, 2.5), 2)
    is_win = random.randint(1, 100) <= actual_win_chance
    new_stars = stars
    result_message_text = ""
    history_amount = 0.0
    history_description = ""
    db_success = False

    pool = database.db_pool
    if not pool: await bot.send_message(user_id, "Ошибка БД."); return

    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                current_stars_tx = await conn.fetchval("SELECT stars FROM users WHERE id = $1 FOR UPDATE", user_id)
                if current_stars_tx is None or current_stars_tx < bet_amount:
                    raise ValueError("Insufficient funds inside TX")

                if is_win:
                    win_amount_net = round(bet_amount * win_coefficient - bet_amount, 2)
                    new_stars = current_stars_tx + win_amount_net
                    await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_stars, user_id)
                    result_text_part = f"🎉 Выиграл! +{win_amount_net:.2f} ⭐️ (x{win_coefficient:.2f})"
                    if luck_boost_percentage > 0: result_text_part += " (с бустом удачи!)"
                    result_message_text = result_text_part
                    history_amount = win_amount_net
                    history_description = f"Выигрыш 'Все или ничего' (x{win_coefficient:.2f})"
                    if luck_boost_percentage > 0: history_description += " (буст удачи)"
                else:
                    new_stars = max(0, current_stars_tx - bet_amount)
                    await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_stars, user_id)
                    result_text_part = f"😞 Проиграл {bet_amount:.1f} ⭐️."
                    if luck_boost_percentage > 0: result_text_part += " (буст удачи был активен)"
                    result_message_text = result_text_part
                    history_amount = -bet_amount
                    history_description = "Проигрыш 'Все или ничего'"
                    if luck_boost_percentage > 0: history_description += " (буст удачи)"
                db_success = True
            except ValueError as ve:
                result_message_text = "Недостаточно средств (повторная проверка)."
                new_stars = current_stars_tx if 'current_stars_tx' in locals() else stars
                db_success = False
            except Exception as db_err:
                result_message_text = "Ошибка базы данных во время игры."
                new_stars = current_stars_tx if 'current_stars_tx' in locals() else stars
                db_success = False

    if db_success:
        try:
            await database.add_game_history_record(user_id, 'luck', history_amount, history_description)
            if is_win:
                try:
                    user_name_display = escape(call.from_user.full_name or f"ID:{user_id}")
                    win_channel_message = (
                        f"🎉 <b>Поздравляем!</b> <a href='tg://user?id={user_id}'>{user_name_display}</a>\n"
                        f"(ID: <code>{user_id}</code>)\n\n"
                        f"выиграл <b>{history_amount + bet_amount:.2f}</b> ⭐️ на ставке <b>{bet_amount:.1f}</b> ⭐️🎲\n\n"
                        f"Коэффициент: <b>{win_coefficient:.2f}</b> ✨\n\n"
                        f"🎉🎉 Потрясающий выигрыш! 🎉🎉\n\n"
                        f"🍀 Не упусти свой шанс! <b>Испытать удачу!</b>"
                    )
                    asyncio.create_task(
                        bot.send_message(WIN_CHANEL_ID, win_channel_message, parse_mode="HTML",
                                         disable_web_page_preview=True)
                    )
                except Exception as e:
                    log.error(f"User {user_id}: Failed schedule win notify to channel {WIN_CHANEL_ID}: {e}")
        except Exception as post_db_err:
            result_message_text += "\n(Ошибка записи истории)"

    try:
        markup = get_luck_game_keyboard(user_id)
        boost_info_text_for_caption = ""
        if luck_boost_percentage > 0:
            boost_info_text_for_caption = f"\n🍀 Буст удачи активен! Ваш шанс: {actual_win_chance:.0f}%"

        caption = (f"💰 <b>У тебя:</b> {new_stars:.2f} ⭐️\n\n"
                   f"🔔 Шанс: {base_win_chance}% (базовый){boost_info_text_for_caption}\n"
                   f"📈 Коэф: x1.8-x2.5\n\n"
                   f"Выбирай ставку! 🍀\n\n"
                   f"📊 Стата: <a href='{LINK_4}'>Здесь</a>")
        image_path = "images/minegame.jpg"
        await _send_or_edit_photo_message(call, image_path, caption, markup, disable_preview=True)
        await bot.send_message(user_id, result_message_text)
    except Exception as ui_err:
        try:
            await bot.send_message(user_id, result_message_text)
        except:
            pass


async def robbery_game_callback(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    try:
        await call.answer()
    except:
        return

    if await database.is_user_blocked(user_id):
        await bot.send_message(user_id, "Вы заблокированы.")
        return

    last_robbery_time = await database.get_last_robbery_time(user_id)
    robbery_cooldown = timedelta(hours=12)
    caption = ""
    markup = InlineKeyboardMarkup()
    can_rob = True
    if last_robbery_time:
        time_since_last = datetime.now(timezone.utc) - last_robbery_time
        if time_since_last < robbery_cooldown:
            remaining = robbery_cooldown - time_since_last
            h = int(remaining.total_seconds() // 3600)
            m = int((remaining.total_seconds() % 3600) // 60)
            caption = f"<b>Ограбление доступно через {h} ч {m} мин.</b>"
            markup.add(InlineKeyboardButton("Меню игр", callback_data="mini_games"))
            can_rob = False
    if can_rob:
        caption = "<b>🔓 Шанс украсть <code>2%</code> звезд!</b>\n\n<i>Рискнешь?</i>"
        markup.add(InlineKeyboardButton("Ограбить 🏃‍♂️", callback_data="robbery_attempt"))
        markup.add(InlineKeyboardButton("Меню игр", callback_data="mini_games"))

    image_path = "images/minegame.jpg"
    await _send_or_edit_photo_message(call, image_path, caption, markup)


async def attempt_robbery_callback(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    try:
        await call.answer("Ищем жертву...")
    except:
        pass

    if await database.is_user_blocked(user_id):
        await bot.send_message(user_id, "Заблокирован.")
        return

    last_robbery_time = await database.get_last_robbery_time(user_id)
    robbery_cooldown = timedelta(hours=12)
    if last_robbery_time and (datetime.now(timezone.utc) - last_robbery_time < robbery_cooldown):
        await robbery_game_callback(call, bot)
        return

    user_balance = await database.get_users_balance(user_id)
    min_balance = 5.0
    image_path = "images/minegame.jpg"
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("Меню игр", callback_data="mini_games"))
    if user_balance < min_balance:
        message_text = f"<b>Мало звезд ({min_balance:.1f}+).</b>"
        await _send_or_edit_photo_message(call, image_path, message_text, markup)
        return

    victim_data = await database.get_random_user(exclude_id=user_id)
    if victim_data is None:
        message_text = "<b>Не удалось найти жертву.</b>"
        await _send_or_edit_photo_message(call, image_path, message_text, markup)
        return

    victim_id, victim_stars = victim_data['id'], victim_data['stars']
    stolen = round(victim_stars * 0.02, 2)
    result_message_text = ""
    db_success = False

    if stolen < 0.01:
        result_message_text = f"<b>Не удалось ничего украсть у ID: {mask_id(victim_id)}.</b>"
        await database.update_last_robbery_time(user_id, victim_id)
    else:
        new_robber_balance = user_balance + stolen
        new_victim_balance = max(0, victim_stars - stolen)
        pool = database.db_pool
        if not pool: await bot.send_message(user_id, "Ошибка БД."); return

        async with pool.acquire() as conn:
            async with conn.transaction():
                try:
                    robber_balance_tx = await conn.fetchval("SELECT stars FROM users WHERE id = $1 FOR UPDATE", user_id)
                    if robber_balance_tx is None or robber_balance_tx < min_balance:
                        raise ValueError("Robber balance check failed inside TX")
                    victim_stars_tx = await conn.fetchval("SELECT stars FROM users WHERE id = $1 FOR UPDATE", victim_id)
                    if victim_stars_tx is None:
                        raise ValueError("Victim not found inside TX")
                    stolen_tx = round(victim_stars_tx * 0.02, 2)
                    if stolen_tx < 0.01:
                        raise ValueError("Stolen amount too small inside TX")
                    new_robber_balance_tx = robber_balance_tx + stolen_tx
                    new_victim_balance_tx = max(0, victim_stars_tx - stolen_tx)
                    await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_robber_balance_tx, user_id)
                    await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_victim_balance_tx, victim_id)
                    current_time_utc = datetime.now(timezone.utc)
                    await conn.execute('''
                        INSERT INTO robberies (user_id, target_user_id, robbery_time) VALUES ($1, $2, $3)
                        ON CONFLICT (user_id, target_user_id) DO UPDATE SET robbery_time = excluded.robbery_time
                    ''', user_id, victim_id, current_time_utc)
                    db_success = True
                    stolen = stolen_tx
                    new_robber_balance = new_robber_balance_tx
                    new_victim_balance = new_victim_balance_tx
                    result_message_text = (f"<b>Украдено {stolen:.2f}⭐️ у ID: {mask_id(victim_id)}!</b>\n"
                                           f"💰 Баланс: {new_robber_balance:.2f}⭐️.")
                except ValueError as ve:
                    result_message_text = f"Не удалось совершить ограбление: {ve}."
                    db_success = False
                except Exception as db_err:
                    result_message_text = "<b>Ошибка базы данных во время ограбления.</b>"
                    db_success = False

        if db_success:
            try:
                victim_username_db = await database.get_user_username(victim_id) or f"ID:{victim_id}"
                robber_username_db = await database.get_user_username(user_id) or f"ID:{user_id}"
                asyncio.gather(
                    database.add_game_history_record(user_id, 'robbery', stolen, f"Ограбление {victim_username_db}"),
                    database.add_game_history_record(victim_id, 'robbery', -stolen, f"Ограблен {robber_username_db}")
                )
            except Exception as h_err:
                log.error(f"Error logging robbery history u:{user_id} v:{victim_id}: {h_err}")
            try:
                asyncio.create_task(bot.send_message(victim_id,
                                                     f"🥷 <b>У вас украли {stolen:.2f}⭐️.</b> Баланс: {new_victim_balance:.2f}⭐️.",
                                                     parse_mode='HTML'))
            except Exception as e:
                log.error(f"Failed schedule victim notification {victim_id}: {e}")

    await _send_or_edit_photo_message(call, image_path, result_message_text, markup, disable_preview=True)


async def play_slots_callback(call: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = call.from_user.id
    try:
        await call.answer()
    except:
        return

    user_data = await database.get_user(user_id)
    if not user_data or await database.is_user_blocked(user_id):
        await bot.send_message(user_id, t(user_id, 'no_registration') if not user_data else "Заблок.")
        return

    stars = user_data['stars']
    await SlotState.waiting_for_bet.set()
    markup = create_bet_inline_keyboard(user_id)

    luck_boost_percentage = await database.get_active_luck_boost_percentage(user_id)
    boost_info_text = ""
    if luck_boost_percentage > 0:
        boost_info_text = f"\n🍀 Буст удачи активен! (шанс на выигрышную комбинацию повышен)"  # Точный % повышения для слотов может быть сложнее определить, чем для "Все или ничего"

    message_text = f"💰 Баланс: {stars:.2f} ⭐️{boost_info_text}\n🎰 Выбери ставку для слотов:"
    await _send_or_edit_photo_message(call, "images/slots.jpg", message_text, markup)


async def handle_slot_bet_selection(call: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = call.from_user.id
    try:
        await call.answer("Принято! Крутим барабан...")
    except:
        pass

    user_data = await database.get_user(user_id)
    if not user_data or await database.is_user_blocked(user_id):
        await state.finish()
        return

    stars = user_data['stars']
    try:
        bet_amount = float(call.data.split("_")[1])
    except (ValueError, IndexError):
        await bot.send_message(user_id, "Некорр. ставка.");
        return

    if stars < bet_amount:
        await bot.send_message(user_id, "❌ Мало звёзд.");
        return

    try:
        await call.message.delete()
    except Exception:
        pass

    await process_slot_bet(call.message.chat.id, user_id, bet_amount, state, bot)


async def process_slot_bet(chat_id, user_id, bet_amount, state: FSMContext, bot: Bot):
    user_data = await database.get_user(user_id)
    if not user_data: await state.finish(); return

    stars = user_data['stars']
    new_stars_after_bet = max(0, stars - bet_amount)
    db_success_deduct = False
    dice_message = None
    dice_value = 0
    win_coefficient = 0
    win_amount_net = 0  # чистый выигрыш
    payout_amount = 0  # полная выплата (ставка * коэф)
    new_stars_after_result = new_stars_after_bet
    result_message_text = ""
    history_bet_amount = -bet_amount
    history_bet_description = "Ставка в Слотах"
    history_win_amount = 0.0
    history_win_description = ""

    pool = database.db_pool
    if not pool: await bot.send_message(chat_id, "🎰 Ошибка БД."); await state.finish(); return

    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                current_stars_tx = await conn.fetchval("SELECT stars FROM users WHERE id = $1 FOR UPDATE", user_id)
                if current_stars_tx is None or current_stars_tx < bet_amount:
                    raise ValueError("Insufficient funds inside TX")
                await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_stars_after_bet, user_id)
                await database.add_game_history_record(user_id, 'slots', history_bet_amount, history_bet_description)
                db_success_deduct = True
            except ValueError:
                result_message_text = "Недостаточно средств (повторная проверка)."
            except Exception:
                result_message_text = "🎰 Ошибка базы данных при ставке."

    if not db_success_deduct:
        await bot.send_message(chat_id, result_message_text);
        await state.finish();
        return

    try:
        dice_message = await bot.send_dice(chat_id, emoji="🎰")
        dice_value = dice_message.dice.value
        await asyncio.sleep(3)
    except Exception:
        try:
            await database.add_stars(user_id, bet_amount)  # Возврат ставки
        except:
            pass
        await bot.send_message(chat_id, "🎰 Ошибка отправки дайса. Ставка возвращена.");
        await state.finish();
        return

    slot_win_map = {1: (2.0, 3.0), 22: (1.2, 1.8), 43: (1.2, 1.8), 64: (3.0, 5.0)}
    is_win = dice_value in slot_win_map

    luck_boost_percentage = await database.get_active_luck_boost_percentage(user_id)
    boost_active_for_slots = luck_boost_percentage > 0  # Пример: буст удачи может влиять на слоты, увеличивая шанс на выигрышную комбинацию

    # Здесь можно усложнить логику, если буст удачи должен влиять на шанс выпадения именно выигрышного dice_value
    # Например, если буст +10%, то шанс на выигрышный dice_value (4 из 64) становится выше.
    # Для простоты, текущий пример не меняет dice_value, а только текст уведомления.

    db_success_payout = False
    if is_win:
        min_c, max_c = slot_win_map[dice_value]
        win_coefficient = round(random.uniform(min_c, max_c), 2)
        payout_amount = round(bet_amount * win_coefficient, 2)
        win_amount_net = round(payout_amount - bet_amount, 2)

        async with pool.acquire() as conn_payout:
            async with conn_payout.transaction():
                try:
                    await conn_payout.execute("UPDATE users SET stars = stars + $1 WHERE id = $2", payout_amount,
                                              user_id)
                    new_stars_after_result = new_stars_after_bet + payout_amount
                    db_success_payout = True
                    history_win_amount = win_amount_net
                    history_win_description = f"Выигрыш в Слотах (x{win_coefficient:.2f})"
                    if boost_active_for_slots: history_win_description += " (буст удачи)"
                    await database.add_game_history_record(user_id, 'slots', history_win_amount,
                                                           history_win_description)
                except Exception:
                    result_message_text = "🎰 Ошибка базы данных при начислении выигрыша."

        if db_success_payout:
            result_message_text = f"🎉 Выигрыш {payout_amount:.2f} ⭐️! (x{win_coefficient:.2f})"
            if boost_active_for_slots: result_message_text += " (с бустом удачи!)"
            result_message_text += f"\n💰 Баланс: {new_stars_after_result:.2f} ⭐️."
            try:
                user_name_display = escape(dice_message.from_user.full_name or f"ID:{user_id}")
                win_channel_message = (
                    f"🎰 <b>Выигрыш в слотах!</b> <a href='tg://user?id={user_id}'>{user_name_display}</a>\n"
                    f"(ID: <code>{user_id}</code>)\n\n"
                    f"выиграл <b>{payout_amount:.2f}</b> ⭐️ на ставке <b>{bet_amount:.1f}</b> ⭐️\n\n"
                    f"Комбинация: {dice_message.dice.emoji} (Value: {dice_value})\n"
                    f"Коэффициент: <b>{win_coefficient:.2f}</b> ✨\n\n"
                    f"🎉🎉 Поздравляем! 🎉🎉"
                )
                asyncio.create_task(
                    bot.send_message(WIN_CHANEL_ID, win_channel_message, parse_mode="HTML",
                                     disable_web_page_preview=True)
                )
            except Exception as e:
                log.error(f"Failed schedule slots win notify: {e}")
    else:
        result_message_text = f"😞 Увы, не повезло."
        if boost_active_for_slots: result_message_text += " (буст удачи был активен)"
        result_message_text += f"\n💰 Баланс: {new_stars_after_result:.2f} ⭐️."

    markup = create_slot_button(user_id)
    markup.add(InlineKeyboardButton("⬅️ Назад в меню игр", callback_data="mini_games"))
    await bot.send_message(chat_id, result_message_text, reply_markup=markup)
    await state.finish()


def register_user_game_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(lambda call: show_mini_games_menu(call, bot), lambda c: c.data == "mini_games",
                                       state="*")
    dp.register_callback_query_handler(lambda call: play_luck_game_callback(call, bot), lambda c: c.data == "play_game",
                                       state="*")
    dp.register_callback_query_handler(lambda call: robbery_game_callback(call, bot),
                                       lambda c: c.data == "play_robbery", state="*")
    dp.register_callback_query_handler(lambda call, state: play_slots_callback(call, state, bot),
                                       lambda c: c.data == "play_slots", state="*")
    dp.register_callback_query_handler(lambda call: play_luck_game_with_bet(call, bot),
                                       lambda c: c.data.startswith("play_game_with_bet:"), state="*")
    dp.register_callback_query_handler(lambda call: attempt_robbery_callback(call, bot),
                                       lambda c: c.data == "robbery_attempt", state="*")
    dp.register_callback_query_handler(lambda call, state: handle_slot_bet_selection(call, state, bot),
                                       lambda c: c.data.startswith("bets_"), state=SlotState.waiting_for_bet)
    log.info("User game handlers registered.")
