# Содержимое файла: handlers/admin_users.py (Адаптировано для asyncpg)
import logging
import asyncpg  # <-- Добавлено
from html import escape

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import BadRequest

import database  # Наш async database
from settings import ADMIN_IDS
from utils import t, format_datetime, show_advert
from keyboards import create_profile_actions_markup, create_admin_cancel_markup
from states import UserIDState

log = logging.getLogger('handlers.admin_users')


async def _update_user_profile_message(message: types.Message, user_id_to_show: int, bot: Bot):
    log.debug(f"Updating profile message for user {user_id_to_show}")
    pool = database.db_pool
    if not pool: log.error("DB pool not initialized for profile update!"); return

    async with pool.acquire() as conn:
        try:
            user_data = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id_to_show)  # await
            if not user_data:
                await message.edit_text("❌ Пользователь не найден.", reply_markup=create_admin_cancel_markup())
                return

            block_record = await conn.fetchrow('SELECT is_blocked FROM block_status WHERE user_id = $1',
                                               user_id_to_show)  # await
            block_status_str = "🟢 Активен (нет записи)"
            if block_record:
                block_status_str = "🔴 Заблокирован" if block_record['is_blocked'] == 1 else "🟢 Активен"

            current_username_db = user_data['username']
            try:
                user_info_tg = await bot.get_chat(user_id_to_show)
                telegram_username = user_info_tg.username or f"id_{user_id_to_show}"
                if current_username_db != telegram_username:
                    await conn.execute("UPDATE users SET username = $1 WHERE id = $2", telegram_username,
                                       user_id_to_show)  # await
                    log.info(f"Refreshed username for {user_id_to_show} to '{telegram_username}' during profile update")
                    # Обновляем локальную переменную для отображения
                    current_username_db = telegram_username
            except Exception as tg_err:
                log.warning(f"Could not refresh username for {user_id_to_show} during update: {tg_err}")

            id_db = user_data['id']
            stars_db = user_data['stars']
            referral_id_db = user_data['referral_id']
            withdrawn_db = user_data['withdrawn']
            lang_db = user_data['lang']
            last_click_time_db = user_data['last_click_time']
            last_gift_time_db = user_data['last_gift_time']
            click_count_db = user_data['click_count']
            gift_count_db = user_data['gift_count']
            registration_time_db = user_data['registration_time']
            special_ref_db = user_data['special_ref']

            ref_count_actual = await database.get_referrals_count(id_db)  # await
            formatted_reg_time = format_datetime(registration_time_db)
            formatted_click_time = format_datetime(last_click_time_db)
            formatted_gift_time = format_datetime(last_gift_time_db)

            response_text = (
                f"🧾 <b>Информация о пользователе</b>:\n\n"
                f"👤 ID: <code>{id_db}</code>\n"
                f"📛 Username: @{current_username_db or '—'}\n"
                f"⭐️ Баланс: {stars_db:.2f}\n"
                f"💰 Выведено: {withdrawn_db:.2f}\n"
                f"🔗 ID реферера: {referral_id_db or '—'}\n"
                f"👥 Рефералов: {ref_count_actual}\n"
                f"🔖 Спец. ссылка: {special_ref_db or 'Нет'}\n"
                f"🌍 Язык: {lang_db}\n"
                f"🖱 Клики: {click_count_db} (последний: {formatted_click_time})\n"
                f"🎁 Подарки: {gift_count_db} (последний: {formatted_gift_time})\n"
                f"📅 Регистрация: <code>{formatted_reg_time}</code>\n"
                f"🚦 Статус: <b>{block_status_str}</b>"
            )
            keyboard = create_profile_actions_markup(id_db, block_status_str)
            await message.edit_text(response_text, reply_markup=keyboard, parse_mode="HTML")

        except BadRequest as e:
            log.error(f"BadRequest editing profile message user {user_id_to_show}: {e}")
        except asyncpg.PostgresError as db_err:
            log.exception(f"DB error updating profile {user_id_to_show}: {db_err}")
        except Exception as e:
            log.exception(f"Error updating user profile message {user_id_to_show}: {e}")


async def ask_for_user_id(callback_query: CallbackQuery, state: FSMContext):
    bot_instance = callback_query.bot
    if callback_query.from_user.id not in ADMIN_IDS: return
    await callback_query.answer()
    markup = create_admin_cancel_markup(callback_data="cancel_user_search")
    await bot_instance.send_message(callback_query.from_user.id, "Введите ID пользователя (только цифры):",
                                    reply_markup=markup)
    await UserIDState.waiting_for_user_id.set()


async def cancel_user_search_callback(call: CallbackQuery, state: FSMContext):
    await call.answer("Отменено")
    await state.finish()
    markup = create_admin_cancel_markup()
    await call.message.edit_text("Ввод ID отменен.", reply_markup=markup)


async def process_user_id_input(message: types.Message, state: FSMContext, bot: Bot):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return

    user_id_str = message.text.strip()
    if not user_id_str.isdigit():
        await message.reply("❌ Пожалуйста, введите корректный числовой ID.");
        return

    user_id_to_show = int(user_id_str)
    log.info(f"Admin {admin_id} requested info for user {user_id_to_show}")

    pool = database.db_pool
    if not pool: log.error("DB pool not initialized!"); await message.reply("Ошибка БД."); await state.finish(); return

    async with pool.acquire() as conn:
        user_data = None
        block_status_str = "🟢 Активен (нет записи)"
        try:
            user_data = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id_to_show)
            if not user_data:
                markup = create_admin_cancel_markup()
                await message.reply("❌ Пользователь с таким ID не найден.", reply_markup=markup);
                await state.finish();
                return

            block_record = await conn.fetchrow('SELECT is_blocked FROM block_status WHERE user_id = $1',
                                               user_id_to_show)
            if block_record: block_status_str = "🔴 Заблокирован" if block_record['is_blocked'] == 1 else "🟢 Активен"

            current_username_db = user_data['username']
            try:
                user_info_tg = await bot.get_chat(user_id_to_show)
                telegram_username = user_info_tg.username or f"id_{user_id_to_show}"
                if current_username_db != telegram_username:
                    await conn.execute("UPDATE users SET username = $1 WHERE id = $2", telegram_username,
                                       user_id_to_show)
                    log.info(
                        f"Updated username for {user_id_to_show} from '{current_username_db}' to '{telegram_username}'")
                    current_username_db = telegram_username
            except BadRequest as e:
                log.warning(f"BadRequest fetching username for {user_id_to_show}: {e}. Using stored.")
            except Exception as tg_err:
                log.warning(f"Could not fetch/update username from Telegram {user_id_to_show}: {tg_err}")

            id_db = user_data['id']
            stars_db = user_data['stars']
            referral_id_db = user_data['referral_id']
            withdrawn_db = user_data['withdrawn']
            lang_db = user_data['lang']
            last_click_time_db = user_data['last_click_time']
            last_gift_time_db = user_data['last_gift_time']
            click_count_db = user_data['click_count']
            gift_count_db = user_data['gift_count']
            registration_time_db = user_data['registration_time']
            special_ref_db = user_data['special_ref']

            ref_count_actual = await database.get_referrals_count(id_db)  # await
            formatted_reg_time = format_datetime(registration_time_db)
            formatted_click_time = format_datetime(last_click_time_db)
            formatted_gift_time = format_datetime(last_gift_time_db)

            response_text = (
                f"🧾 <b>Информация о пользователе</b>:\n\n"
                f"👤 ID: <code>{id_db}</code>\n"
                f"📛 Username: @{current_username_db or '—'}\n"
                f"⭐️ Баланс: {stars_db:.2f}\n"
                f"💰 Выведено: {withdrawn_db:.2f}\n"
                f"🔗 ID реферера: {referral_id_db or '—'}\n"
                f"👥 Рефералов: {ref_count_actual}\n"
                f"🔖 Спец. ссылка: {special_ref_db or 'Нет'}\n"
                f"🌍 Язык: {lang_db}\n"
                f"🖱 Клики: {click_count_db} (последний: {formatted_click_time})\n"
                f"🎁 Подарки: {gift_count_db} (последний: {formatted_gift_time})\n"
                f"📅 Регистрация: <code>{formatted_reg_time}</code>\n"
                f"🚦 Статус: <b>{block_status_str}</b>"
            )
            keyboard = create_profile_actions_markup(id_db, block_status_str)
            await message.answer(response_text, reply_markup=keyboard, parse_mode="HTML")
            await state.finish()

        except BadRequest as e:
            markup = create_admin_cancel_markup()
            if "user not found" in str(e).lower() or "chat not found" in str(e).lower():
                await message.reply("❌ Пользователь с таким ID не найден в Telegram.", reply_markup=markup)
            elif "bot was blocked by the user" in str(e).lower():
                await message.reply("❌ Бот заблокирован этим пользователем.", reply_markup=markup)
            else:
                log.exception(f"Telegram API error fetching info for {user_id_to_show}: {e}"); await message.reply(
                    f"❌ Ошибка Telegram API: {e}", reply_markup=markup)
            await state.finish()
        except asyncpg.PostgresError as db_err:
            log.exception(f"Database error fetching info for user {user_id_to_show}: {db_err}")
            await message.reply("❌ Ошибка базы данных при поиске.", reply_markup=create_admin_cancel_markup());
            await state.finish()
        except Exception as e:
            log.exception(f"Unexpected error fetching info for user {user_id_to_show}: {e}")
            await message.reply("❌ Непредвиденная ошибка.", reply_markup=create_admin_cancel_markup());
            await state.finish()


async def block_user_callback(callback_query: CallbackQuery, bot: Bot):
    admin_id = callback_query.from_user.id
    if admin_id not in ADMIN_IDS: await callback_query.answer("⛔ Нет доступа!", show_alert=True); return

    try:
        user_id_to_block = int(callback_query.data.split("_")[1])
    except (IndexError, ValueError):
        await callback_query.answer("Ошибка ID.", show_alert=True); return

    log.info(f"Admin {admin_id} attempting to block user {user_id_to_block}")
    success = await database.block_user_in_db(user_id_to_block)  # await

    if success:
        await callback_query.answer("Пользователь заблокирован.", show_alert=False)
        await _update_user_profile_message(callback_query.message, user_id_to_block, bot)  # await
        try:
            await bot.send_message(user_id_to_block, "❌ Ваш аккаунт был заблокирован администрацией.")
        except Exception as e:
            log.warning(f"Failed to notify user {user_id_to_block} about blocking: {e}")
    else:
        await callback_query.answer("Не удалось заблокировать (уже заблок. или ошибка).", show_alert=True)


async def unblock_user_callback(callback_query: CallbackQuery, bot: Bot):
    admin_id = callback_query.from_user.id
    if admin_id not in ADMIN_IDS: await callback_query.answer("⛔ Нет доступа!", show_alert=True); return

    try:
        user_id_to_unblock = int(callback_query.data.split("_")[1])
    except (IndexError, ValueError):
        await callback_query.answer("Ошибка ID.", show_alert=True); return

    log.info(f"Admin {admin_id} attempting to unblock user {user_id_to_unblock}")
    success = await database.unblock_user_in_db(user_id_to_unblock)  # await

    if success:
        await callback_query.answer("Пользователь разблокирован.", show_alert=False)
        await _update_user_profile_message(callback_query.message, user_id_to_unblock, bot)  # await
        try:
            await bot.send_message(user_id_to_unblock, "✅ Ваш аккаунт был разблокирован администрацией.")
        except Exception as e:
            log.warning(f"Failed to notify user {user_id_to_unblock} about unblocking: {e}")
    else:
        await callback_query.answer("Не удалось разблокировать (не заблок. или ошибка).", show_alert=True)


async def ask_star_amount(callback_query: CallbackQuery, state: FSMContext):
    admin_id = callback_query.from_user.id
    bot_instance = callback_query.bot
    if admin_id not in ADMIN_IDS: return
    await callback_query.answer()

    try:
        parts = callback_query.data.split("_")
        action_type = parts[0]
        user_id_target = int(parts[-1])
    except (IndexError, ValueError):
        await callback_query.message.reply("Ошибка в данных кнопки."); return

    await state.update_data(target_user_id=user_id_target, action=action_type)
    await UserIDState.waiting_for_star_amount.set()
    prompt_text = "➕ Введите количество звезд для ДОБАВЛЕНИЯ:" if action_type == "add" else "➖ Введите количество звезд для СПИСАНИЯ:"
    markup = create_admin_cancel_markup(callback_data="cancel_star_operation")
    await bot_instance.send_message(admin_id, prompt_text, reply_markup=markup)


async def cancel_star_operation_callback(call: CallbackQuery, state: FSMContext):
    await call.answer("Отменено")
    await state.finish()
    markup = create_admin_cancel_markup()
    await call.message.edit_text("Операция отменена.", reply_markup=markup)


async def process_star_amount_input(message: types.Message, state: FSMContext, bot: Bot):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return

    try:
        stars_amount = float(message.text.strip())
        if stars_amount <= 0: await message.reply("❌ Количество звезд должно быть положительным."); return
    except ValueError:
        await message.reply("❌ Введите корректное число."); return

    user_data = await state.get_data()
    target_user_id = user_data.get('target_user_id')
    action = user_data.get('action')
    markup = create_admin_cancel_markup()

    if not target_user_id or not action:
        await message.reply("❗ Ошибка состояния. Начните заново.", reply_markup=markup);
        await state.finish();
        return

    try:
        if action == 'add':
            await database.add_stars(target_user_id, stars_amount)  # await
            log.info(f"Admin {admin_id} added {stars_amount} stars to user {target_user_id}")
            await message.answer(f"✅ Звезды ({stars_amount:.2f}) добавлены ID {target_user_id}.", reply_markup=markup)
            try:
                await bot.send_message(target_user_id, f"✨ Администрация добавила вам <b>{stars_amount:.2f}⭐️</b>!",
                                       parse_mode="HTML")
            except Exception as e:
                log.warning(f"Failed to notify user {target_user_id} added stars: {e}")
            # await show_advert(target_user_id) # await, если стала async

        elif action == 'subtract':
            current_balance = await database.get_users_balance(target_user_id)  # await
            if stars_amount > current_balance:
                await message.reply(f"❌ Нельзя списать {stars_amount:.2f}. Баланс: {current_balance:.2f}⭐️.",
                                    reply_markup=markup);
                await state.finish();
                return

            await database.subtract_stars(target_user_id, stars_amount)  # await
            log.info(f"Admin {admin_id} subtracted {stars_amount} stars from user {target_user_id}")
            await message.answer(f"✅ Звезды ({stars_amount:.2f}) списаны у ID {target_user_id}.", reply_markup=markup)
            try:
                await bot.send_message(target_user_id, f"🔻 Администрация списала у вас <b>{stars_amount:.2f}⭐️</b>.",
                                       parse_mode="HTML")
            except Exception as e:
                log.warning(f"Failed to notify user {target_user_id} subtracted stars: {e}")

    except Exception as e:
        log.exception(f"Error processing star amount user {target_user_id} admin {admin_id}: {e}")
        await message.answer("❌ Ошибка изменения баланса.", reply_markup=markup)

    await state.finish()


async def ask_set_reward(callback_query: CallbackQuery, state: FSMContext):
    admin_id = callback_query.from_user.id
    bot_instance = callback_query.bot
    if admin_id not in ADMIN_IDS: return
    await callback_query.answer()

    target_user_id_str = None;
    state_to_set = None;
    reward_type = None

    if callback_query.data.startswith("set_click_reward_for_"):
        reward_type = "за клик";
        target_user_id_str = callback_query.data[len("set_click_reward_for_"):];
        state_to_set = UserIDState.waiting_for_click_reward
    elif callback_query.data.startswith("set_ref_reward_for_"):
        reward_type = "за реферала";
        target_user_id_str = callback_query.data[len("set_ref_reward_for_"):];
        state_to_set = UserIDState.waiting_for_ref_reward
    else:
        log.error(f"Unknown reward setting callback: {callback_query.data}"); return

    if target_user_id_str and target_user_id_str.isdigit():
        target_user_id = int(target_user_id_str)
        await state.update_data(target_user_id_for_reward=target_user_id)
        await state.set_state(state_to_set)
        markup = create_admin_cancel_markup(callback_data="cancel_reward_setting")
        await bot_instance.send_message(admin_id,
                                        f"Введите диапазон награды {reward_type} для ID <code>{target_user_id}</code> в формате:\n<code>min:max</code>\n(например: 0.1:0.5)",
                                        parse_mode="HTML", reply_markup=markup)
    else:
        log.error(f"Could not extract user ID from reward callback: {callback_query.data}")
        await callback_query.answer("Ошибка получения ID.", show_alert=True)


async def cancel_reward_setting_callback(call: CallbackQuery, state: FSMContext):
    await call.answer("Отменено")
    await state.finish()
    markup = create_admin_cancel_markup()
    await call.message.edit_text("Настройка награды отменена.", reply_markup=markup)


async def process_set_reward_input(message: types.Message, state: FSMContext, bot: Bot):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return

    current_state_str = await state.get_state()
    is_click_reward = current_state_str == UserIDState.waiting_for_click_reward.state
    is_ref_reward = current_state_str == UserIDState.waiting_for_ref_reward.state

    if not (is_click_reward or is_ref_reward): await state.finish(); return

    state_data = await state.get_data()
    target_user_id = state_data.get('target_user_id_for_reward')
    markup = create_admin_cancel_markup()

    if not target_user_id:
        await message.reply("❗ Ошибка: ID пользователя не найден. Начните заново.", reply_markup=markup);
        await state.finish();
        return

    try:
        if ':' not in message.text: raise ValueError("Invalid format, missing colon")
        min_val_str, max_val_str = message.text.split(':', 1)
        min_val = float(min_val_str.strip())
        max_val = float(max_val_str.strip())
        if min_val < 0 or max_val < 0 or min_val > max_val: raise ValueError("Invalid reward range")

        if is_click_reward:
            await database.set_custom_reward_in_db(target_user_id, min_val, max_val)  # await
            reward_type_str = "за клик"
        else:  # is_ref_reward
            await database.set_ref_reward(target_user_id, min_val, max_val)  # await
            reward_type_str = "за реферала"

        log.info(f"Admin {admin_id} set custom {reward_type_str} reward user {target_user_id} to {min_val}:{max_val}")
        await message.answer(
            f"✅ Награда {reward_type_str} для ID {target_user_id} установлена: от {min_val:.2f}⭐ до {max_val:.2f}⭐.",
            reply_markup=markup)
        await state.finish()

    except (ValueError, IndexError) as e:
        await message.reply(f"❌ Неверный формат ({e}). Используйте: <code>min:max</code>\nПример: 0.1:0.5",
                            reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        log.exception(f"Error setting custom reward admin {admin_id}: {e}")
        await message.answer("❌ Ошибка при установке награды.", reply_markup=markup);
        await state.finish()


async def delete_user_command(message: types.Message):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await message.reply("⛔ Нет прав."); return

    args = message.text.split()
    if len(args) < 2: await message.reply("❓ /deleteuser <user_id>", parse_mode="Markdown"); return

    try:
        user_id_to_delete = int(args[1])
        log.warning(f"Admin {admin_id} initiated deletion of user {user_id_to_delete}")
        confirm_markup = InlineKeyboardMarkup(row_width=2)
        confirm_markup.add(InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{user_id_to_delete}"))
        confirm_markup.add(InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_delete"))
        await message.reply(f"⚠️ Удалить пользователя ID {user_id_to_delete}? Действие необратимо!",
                            reply_markup=confirm_markup)
    except ValueError:
        await message.reply("❌ Укажите корректный числовой ID.")
    except Exception as e:
        log.exception(
            f"Error initiating deletion {args[1] if len(args) > 1 else ''} admin {admin_id}: {e}"); await message.reply(
            "❌ Ошибка инициации удаления.")


async def confirm_delete_user_callback(call: CallbackQuery):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: await call.answer("Нет доступа!", show_alert=True); return

    try:
        user_id_to_delete = int(call.data.split("_")[-1])
    except (ValueError, IndexError):
        await call.answer("Ошибка ID.", show_alert=True); return

    await call.answer(f"Удаляю пользователя {user_id_to_delete}...")
    try:
        deleted = await database.delete_user(user_id_to_delete)  # await
        if deleted:
            await call.message.edit_text(f"✅ Пользователь ID {user_id_to_delete} удален.",
                                         reply_markup=create_admin_cancel_markup())
            log.warning(f"Admin {admin_id} confirmed deletion of user {user_id_to_delete}.")
        else:
            await call.message.edit_text(f"❌ Пользователь ID {user_id_to_delete} не найден.",
                                         reply_markup=create_admin_cancel_markup())
    except Exception as e:
        log.exception(f"Error deleting user {user_id_to_delete} admin {admin_id}: {e}")
        await call.message.edit_text("❌ Ошибка при удалении.", reply_markup=create_admin_cancel_markup())


async def cancel_delete_user_callback(call: CallbackQuery):
    await call.answer("Удаление отменено")
    await call.message.edit_text("Удаление пользователя отменено.", reply_markup=create_admin_cancel_markup())


def register_admin_user_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(ask_for_user_id, lambda c: c.data == "get_user_id", state="*")
    dp.register_callback_query_handler(cancel_user_search_callback, lambda c: c.data == "cancel_user_search",
                                       state=UserIDState.waiting_for_user_id)
    dp.register_message_handler(lambda msg, state: process_user_id_input(msg, state, bot),
                                state=UserIDState.waiting_for_user_id)
    dp.register_callback_query_handler(lambda call: block_user_callback(call, bot),
                                       lambda c: c.data.startswith("block_"), state="*")
    dp.register_callback_query_handler(lambda call: unblock_user_callback(call, bot),
                                       lambda c: c.data.startswith("unblock_"), state="*")
    dp.register_callback_query_handler(ask_star_amount, lambda c: c.data.startswith("add_stars_") or c.data.startswith(
        "subtract_stars_"), state="*")
    dp.register_callback_query_handler(cancel_star_operation_callback, lambda c: c.data == "cancel_star_operation",
                                       state=UserIDState.waiting_for_star_amount)
    dp.register_message_handler(lambda msg, state: process_star_amount_input(msg, state, bot),
                                state=UserIDState.waiting_for_star_amount)
    dp.register_callback_query_handler(ask_set_reward,
                                       lambda c: c.data.startswith("set_click_reward_for_") or c.data.startswith(
                                           "set_ref_reward_for_"), state="*")
    dp.register_callback_query_handler(cancel_reward_setting_callback, lambda c: c.data == "cancel_reward_setting",
                                       state=[UserIDState.waiting_for_click_reward, UserIDState.waiting_for_ref_reward])
    dp.register_message_handler(lambda msg, state: process_set_reward_input(msg, state, bot),
                                state=UserIDState.waiting_for_click_reward)
    dp.register_message_handler(lambda msg, state: process_set_reward_input(msg, state, bot),
                                state=UserIDState.waiting_for_ref_reward)
    dp.register_message_handler(delete_user_command, commands=['deleteuser'], state="*")
    dp.register_callback_query_handler(confirm_delete_user_callback, lambda c: c.data.startswith("confirm_delete_"),
                                       state="*")
    dp.register_callback_query_handler(cancel_delete_user_callback, lambda c: c.data == "cancel_delete", state="*")
    log.info("Admin user management handlers registered.")
