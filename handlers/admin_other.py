import logging
import os
import asyncpg
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputFile
from aiogram.utils.exceptions import MessageNotModified, ChatNotFound, BotBlocked, UserDeactivated
from aiogram.dispatcher import FSMContext

import database
from settings import ADMIN_IDS, USER_BOT, AVAILABLE_DAILY_GIFTS, DEFAULT_DAILY_GIFT_KEY
from utils import t, generate_filename as utils_generate_filename
from keyboards import create_admin_cancel_markup, create_inline_menu, create_admin_panel_markup, \
    create_cancel_direct_message_markup
from states import ProjectBalanceState, GiveStars as GiveStarsState, AdminDirectMessageState
from handlers.admin_panel import show_admin_panel

log = logging.getLogger('handlers.admin_other')
log_admin_dm = logging.getLogger('handlers.admin_direct_message')


async def set_lucky_time_callback(call: CallbackQuery, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer()
    try:
        start_time = datetime.now(timezone.utc)
        duration_minutes = 60
        await database.set_lucky_time(start_time, duration_minutes)
        log.info(f"Admin {admin_id} activated lucky time for {duration_minutes} minutes.")
        await bot.send_message(call.message.chat.id, f"✅ Счастливый час активирован на {duration_minutes} минут!")
    except Exception as e:
        log.exception(f"Error activating lucky time admin {admin_id}: {e}")
        await bot.send_message(call.message.chat.id, "❌ Ошибка активации.")


async def set_project_balance_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    markup = create_admin_cancel_markup()
    prompt_text = t(call.from_user.id, 'project_balance_set') or "Введите новый баланс проекта (число):"
    await call.message.edit_text(prompt_text, reply_markup=markup)
    await ProjectBalanceState.waiting_for_balance.set()


async def set_project_balance_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    try:
        new_balance = float(message.text.strip())
        await database.set_project_balance(new_balance)
        log.info(f"Admin {admin_id} set project balance to {new_balance}")
        success_text = t(admin_id, 'project_balance_updated') or "Баланс проекта обновлен!"
        await message.answer(success_text, reply_markup=markup)
        await state.finish()
    except ValueError:
        await message.reply("❌ Введите корректное число.", reply_markup=markup)
    except Exception as e:
        log.exception(f"Error setting project balance admin {admin_id}: {e}")
        await message.answer("❌ Ошибка установки баланса.", reply_markup=markup);
        await state.finish()


async def reset_balances_callback(call: CallbackQuery):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer()
    confirm_markup = InlineKeyboardMarkup(row_width=2)
    confirm_markup.add(InlineKeyboardButton("✅ Да, обнулить", callback_data="confirm_reset_balances"))
    confirm_markup.add(InlineKeyboardButton("❌ Нет, отмена", callback_data="adminpanel"))
    await call.message.edit_text("⚠️ Обнулить балансы ВСЕХ? Необратимо!", reply_markup=confirm_markup)


async def confirm_reset_balances_callback(call: CallbackQuery, bot: Bot, app):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer("Обнуляю балансы...", show_alert=False)
    log.warning(f"Admin {admin_id} confirmed reset all user balances.")
    try:
        reseted_count = await database.reset_user_balances()
        await call.message.edit_text(f"✅ Балансы {reseted_count} пользователей обнулены.",
                                     reply_markup=create_admin_cancel_markup())
        await show_admin_panel(call, bot, app)
    except Exception as e:
        log.exception(f"Error resetting balances admin {admin_id}: {e}")
        await call.message.edit_text("❌ Ошибка обнуления.", reply_markup=create_admin_cancel_markup())


async def give_stars_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    markup = create_admin_cancel_markup()
    await call.message.edit_text("Введите кол-во звезд для выдачи ВСЕМ:", reply_markup=markup)
    await GiveStarsState.amount.set()


async def give_stars_input(message: types.Message, state: FSMContext, bot: Bot, app):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    try:
        amount = float(message.text.strip())
        if amount <= 0: raise ValueError("Amount must be positive")
        log.info(f"Admin {admin_id} initiated giving {amount} stars to all.")
        given_count = await database.give_stars_to_all(amount)
        await message.answer(f"✅ Выдано по {amount:.2f} звезд {given_count} пользователям.", reply_markup=markup)
        await show_admin_panel(message, bot, app)
    except ValueError:
        await message.reply("❌ Введите корректное полож. число.", reply_markup=markup)
    except Exception as e:
        log.exception(f"Error giving stars all admin {admin_id}: {e}")
        await message.answer("❌ Ошибка массовой выдачи.", reply_markup=markup)
    finally:
        await state.finish()


async def db_management_menu(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    keyboard = create_inline_menu()
    try:
        await call.message.edit_text("Экспорт данных из базы:", reply_markup=keyboard)
    except MessageNotModified:
        pass
    except Exception as e:
        log.warning(f"Could not edit msg DB menu: {e}. Send new.");
        await call.message.answer("Экспорт данных:", reply_markup=keyboard)


async def handle_db_export(call: CallbackQuery, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    action = call.data
    await call.answer(f"Подготовка '{action}'...")
    log.info(f"Admin {admin_id} requested DB export: {action}")
    filename = None;
    temp_file_path = None
    try:
        if action == "full_db":
            await call.message.answer("Полный бэкап PostgreSQL делается утилитой `pg_dump`.")
            return
        pool = database.db_pool
        if not pool: raise RuntimeError("DB pool not initialized")
        async with pool.acquire() as conn:
            data_to_write = [];
            filename_prefix = "";
            caption = ""
            if action == "usernames_list":
                rows = await conn.fetch(
                    "SELECT username FROM users WHERE username IS NOT NULL AND username != '' AND not username like 'id_%'")
                data_to_write = [row['username'] for row in rows];
                filename_prefix = "usernames";
                caption = "Список Username"
            elif action == "ids_list":
                rows = await conn.fetch("SELECT id FROM users")
                data_to_write = [str(row['id']) for row in rows];
                filename_prefix = "user_ids";
                caption = "Список ID"
            else:
                await call.message.answer("Неизвестный тип.");
                return
            if not data_to_write: await call.message.answer(f"Нет данных '{action}'."); return
            filename = utils_generate_filename(filename_prefix, extension="txt")
            temp_file_path = filename
            with open(temp_file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(data_to_write))
            log.debug(f"Created temp file {temp_file_path} for {action} export.")
            try:
                await bot.send_document(admin_id, InputFile(temp_file_path),
                                        caption=f"{caption} ({len(data_to_write)} записей)")
            except Exception as send_err:
                log.error(f"Failed send {action} list admin {admin_id}: {send_err}");
                await call.message.answer(f"❌ Ошибка отправки: {send_err}")
    except asyncpg.PostgresError as db_err:
        log.exception(f"DB error {action} export admin {admin_id}: {db_err}");
        await call.message.answer("❌ Ошибка БД.")
    except Exception as e:
        log.exception(f"Error {action} export admin {admin_id}: {e}");
        await call.message.answer("❌ Ошибка экспорта.")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path); log.debug(f"Removed temp export file: {temp_file_path}")
            except OSError as e:
                log.error(f"Error removing temp file {temp_file_path}: {e}")


async def generate_special_link(call: CallbackQuery, state: FSMContext):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer("Генерирую ссылку...")
    pool = database.db_pool
    if not pool: log.error("DB pool not initialized!"); await call.answer("Ошибка БД.", show_alert=True); return
    async with pool.acquire() as conn:
        try:
            special_code = f"ref_{secrets.token_hex(8)}"
            special_link = f"https://t.me/{USER_BOT}?start={special_code}"
            await conn.execute("INSERT INTO special_links (user_id, special_code) VALUES ($1, $2)", admin_id,
                               special_code)
            log.info(f"Admin {admin_id} generated special link: {special_link}")
            await call.message.answer(f"✅ Спецссылка:\n<code>{special_link}</code>\n\n/linkstats для статистики.",
                                      parse_mode="HTML", reply_markup=create_admin_cancel_markup())
        except asyncpg.UniqueViolationError:
            await call.message.answer("❌ Ошибка: код существует.")
        except Exception as e:
            log.exception(f"Error generating special link admin {admin_id}: {e}"); await call.message.answer(
                "❌ Ошибка генерации.")


async def manual_activity_check(message: types.Message, bot: Bot):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await message.reply("⛔ Нет прав."); return
    log.info(f"Admin {admin_id} triggered manual inactive user check.")
    await message.reply("🚀 Запускаю проверку неактивных...")
    from scheduler import check_inactive_users_task
    asyncio.create_task(check_inactive_users_task(bot))


async def show_daily_gift_selection(call: CallbackQuery):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer()
    current_gift_id = await database.get_selected_daily_gift()
    markup = InlineKeyboardMarkup(row_width=1)
    found_current = False
    for gift_name, gift_id_in_dict in AVAILABLE_DAILY_GIFTS.items():
        button_text = gift_name
        if gift_id_in_dict == current_gift_id: button_text = f"✅ {gift_name}"; found_current = True
        markup.add(InlineKeyboardButton(button_text, callback_data=f"set_daily_gift:{gift_id_in_dict}"))
    default_gift_id = AVAILABLE_DAILY_GIFTS.get(DEFAULT_DAILY_GIFT_KEY)
    if found_current and default_gift_id is not None and current_gift_id != default_gift_id:
        markup.add(InlineKeyboardButton("🔄 Сбросить к дефолту", callback_data="set_daily_gift:default"))
    markup.add(InlineKeyboardButton("👑 Админ-меню", callback_data="adminpanel"))
    try:
        await call.message.edit_text("Выберите подарок для топ-рефовода дня:", reply_markup=markup)
    except MessageNotModified:
        pass
    except Exception as e:
        log.error(f"Error editing message daily gift selection: {e}")


async def handle_set_daily_gift(call: CallbackQuery, bot: Bot, app):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    try:
        data_part = call.data.split(":")[1]
        gift_id_to_set = None;
        action_text = ""
        if data_part == "default":
            gift_id_to_set = AVAILABLE_DAILY_GIFTS.get(DEFAULT_DAILY_GIFT_KEY)
            if gift_id_to_set is None: log.error("Default daily gift key not found!"); await call.answer(
                "Ошибка: нет подарка по умолчанию.", show_alert=True); return
            await database.set_selected_daily_gift(gift_id_to_set)
            action_text = "Сброшено к дефолту."
        else:
            gift_id_to_set = int(data_part)
            if gift_id_to_set not in AVAILABLE_DAILY_GIFTS.values(): await call.answer("Ошибка: Недопустимый ID.",
                                                                                       show_alert=True); return
            await database.set_selected_daily_gift(gift_id_to_set)
            action_text = "Ежедневный подарок обновлен!"
        await call.answer(action_text, show_alert=False)
        await show_daily_gift_selection(call)
    except (IndexError, ValueError) as e:
        log.error(f"Error parsing set_daily_gift cb '{call.data}': {e}");
        await call.answer("Ошибка данных.", show_alert=True)
    except Exception as e:
        log.exception(f"Error setting daily gift: {e}");
        await call.answer("Ошибка сохранения.", show_alert=True)


async def toggle_withdrawals_callback(call: CallbackQuery, bot: Bot, app):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: await call.answer("Нет доступа", show_alert=True); return
    current_status = await database.are_withdrawals_enabled();
    new_status = not current_status
    await database.set_withdrawals_enabled(new_status)
    status_text = "ВКЛЮЧЕН" if new_status else "ВЫКЛЮЧЕН";
    await call.answer(f"Вывод средств: {status_text}", show_alert=False)
    log.info(f"Admin {admin_id} toggled withdrawals to {status_text}")
    await show_admin_panel(call, bot, app)


async def toggle_referrals_callback(call: CallbackQuery, bot: Bot, app):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: await call.answer("Нет доступа", show_alert=True); return
    current_status = await database.are_referrals_enabled();
    new_status = not current_status
    await database.set_referrals_enabled(new_status)
    status_text = "ВКЛЮЧЕНА" if new_status else "ВЫКЛЮЧЕНА";
    await call.answer(f"Реф. программа: {status_text}", show_alert=False)
    log.info(f"Admin {admin_id} toggled referral program to {status_text}")
    await show_admin_panel(call, bot, app)


async def start_direct_message_user_handler(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔ Нет доступа!", show_alert=True)
        return
    await call.answer()
    markup = create_cancel_direct_message_markup()
    await call.message.edit_text(
        "Введите @username или ID пользователя, которому хотите отправить сообщение:",
        reply_markup=markup
    )
    await AdminDirectMessageState.waiting_for_username.set()
    log_admin_dm.info(f"Admin {call.from_user.id} initiated direct message to user.")


async def process_direct_message_username_handler(message: types.Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        await state.finish()
        return

    username_or_id_input = message.text.strip()
    target_user_id = None

    if username_or_id_input.isdigit():
        target_user_id = int(username_or_id_input)
        user_exists_in_db = await database.user_exists(target_user_id)
        if not user_exists_in_db:
            log_admin_dm.warning(
                f"Admin {message.from_user.id} entered ID {target_user_id} not found in local DB, but proceeding.")
    else:
        target_user_id = await database.get_user_id_by_username(username_or_id_input)

    if not target_user_id:
        await message.reply(
            f"❌ Пользователь с '{escape(username_or_id_input)}' не найден в базе. Убедитесь, что пользователь взаимодействовал с ботом и его username актуален, или введите точный User ID.",
            reply_markup=create_cancel_direct_message_markup()
        )
        return

    await state.update_data(target_user_id=target_user_id, target_identifier=username_or_id_input)
    await AdminDirectMessageState.waiting_for_message_content.set()
    await message.answer(
        f"Пользователь найден (ID: {target_user_id}). Теперь отправьте сообщение (текст или фото с подписью):",
        reply_markup=create_cancel_direct_message_markup()
    )


async def process_direct_message_content_handler(message: types.Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        await state.finish()
        return

    message_text = None
    photo_file_id = None

    if message.photo:
        photo_file_id = message.photo[-1].file_id
        message_text = message.caption if message.caption else ""
        await state.update_data(direct_message_text=message_text, direct_message_photo=photo_file_id)
    elif message.text:
        message_text = message.html_text
        await state.update_data(direct_message_text=message_text, direct_message_photo=None)
    else:
        await message.reply(
            "❌ Пожалуйста, отправьте текст или фото с подписью.",
            reply_markup=create_cancel_direct_message_markup()
        )
        return

    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    target_identifier = data.get('target_identifier', 'Неизвестно')
    preview_text_intro = f"<b>Предпросмотр сообщения для {escape(target_identifier)} (ID: {target_user_id}):</b>\n\n"

    confirmation_markup = InlineKeyboardMarkup(row_width=2)
    confirmation_markup.add(InlineKeyboardButton("✅ Отправить", callback_data="confirm_send_direct_message"))
    confirmation_markup.add(InlineKeyboardButton("✏️ Изменить сообщение", callback_data="edit_direct_message_content"))
    confirmation_markup.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_direct_message"))

    if photo_file_id:
        await bot.send_photo(
            chat_id=message.from_user.id,
            photo=photo_file_id,
            caption=preview_text_intro + (message_text if message_text else ""),
            parse_mode="HTML"
        )
    else:
        await bot.send_message(
            chat_id=message.from_user.id,
            text=preview_text_intro + message_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    await message.answer("Подтвердите отправку:", reply_markup=confirmation_markup)
    await AdminDirectMessageState.waiting_for_confirmation.set()


async def handle_direct_message_confirmation_handler(call: CallbackQuery, state: FSMContext, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        await state.finish();
        return
    await call.answer()
    action = call.data

    if action == "confirm_send_direct_message":
        data = await state.get_data()
        target_user_id = data.get('target_user_id')
        message_text = data.get('direct_message_text')
        photo_file_id = data.get('direct_message_photo')
        target_identifier = data.get('target_identifier', str(target_user_id))

        if not target_user_id or (message_text is None and not photo_file_id):
            await call.message.edit_text("❗ Ошибка: Недостаточно данных для отправки. Попробуйте снова.",
                                         reply_markup=create_admin_cancel_markup())
            await state.finish();
            return
        try:
            if photo_file_id:
                await bot.send_photo(target_user_id, photo_file_id, caption=message_text, parse_mode="HTML")
            else:
                await bot.send_message(target_user_id, message_text, parse_mode="HTML", disable_web_page_preview=True)

            success_msg = f"✅ Сообщение успешно отправлено пользователю {escape(target_identifier)} (ID: {target_user_id})."
            log_admin_dm.info(
                f"Admin {admin_id} sent DM to user {target_user_id}. Text: '{str(message_text)[:50]}...', Photo: {'Y' if photo_file_id else 'N'}")
            await call.message.edit_text(success_msg, reply_markup=create_admin_cancel_markup())
        except (BotBlocked, UserDeactivated):
            error_msg = f"❌ Не удалось отправить: Бот заблокирован {escape(target_identifier)} (ID: {target_user_id})."
            log_admin_dm.warning(f"DM to {target_user_id} failed: Bot blocked/user deactivated.")
            await call.message.edit_text(error_msg, reply_markup=create_admin_cancel_markup())
        except ChatNotFound:
            error_msg = f"❌ Не удалось отправить: Чат с {escape(target_identifier)} (ID: {target_user_id}) не найден."
            log_admin_dm.warning(f"DM to {target_user_id} failed: Chat not found.")
            await call.message.edit_text(error_msg, reply_markup=create_admin_cancel_markup())
        except Exception as e:
            error_msg = f"❌ Ошибка при отправке {escape(target_identifier)} (ID: {target_user_id}): {e}"
            log_admin_dm.exception(f"Error sending DM to {target_user_id}: {e}")
            await call.message.edit_text(error_msg, reply_markup=create_admin_cancel_markup())
        await state.finish()
    elif action == "edit_direct_message_content":
        await AdminDirectMessageState.waiting_for_message_content.set()
        await call.message.edit_text("Введите новый текст или отправьте фото с подписью:",
                                     reply_markup=create_cancel_direct_message_markup())
    elif action == "cancel_direct_message":
        await call.message.edit_text("Отправка сообщения отменена.", reply_markup=create_admin_cancel_markup())
        await state.finish()


async def cancel_direct_message_flow_handler(call: CallbackQuery, state: FSMContext, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer("Действие отменено.")
    current_state = await state.get_state()
    log_admin_dm.info(f"Admin {admin_id} cancelled direct message flow from state: {current_state}")
    await state.finish()
    await call.message.edit_text("Отменено. Вы в админ-панели:", reply_markup=await create_admin_panel_markup(admin_id))


def register_admin_direct_message_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(start_direct_message_user_handler,
                                       lambda c: c.data == "admin_direct_message_user", state="*")
    dp.register_message_handler(lambda msg, state: process_direct_message_username_handler(msg, state, bot),
                                state=AdminDirectMessageState.waiting_for_username)
    dp.register_message_handler(lambda msg, state: process_direct_message_content_handler(msg, state, bot),
                                state=AdminDirectMessageState.waiting_for_message_content,
                                content_types=[types.ContentType.TEXT, types.ContentType.PHOTO])
    dp.register_callback_query_handler(lambda call, state: handle_direct_message_confirmation_handler(call, state, bot),
                                       lambda c: c.data in ["confirm_send_direct_message",
                                                            "edit_direct_message_content", "cancel_direct_message"],
                                       state=AdminDirectMessageState.waiting_for_confirmation)
    dp.register_callback_query_handler(lambda call, state: cancel_direct_message_flow_handler(call, state, bot),
                                       lambda c: c.data == "cancel_direct_message",
                                       state=AdminDirectMessageState.all_states)
    log_admin_dm.info("Admin direct message handlers registered.")


def register_admin_other_handlers(dp: Dispatcher, bot: Bot, app):
    dp.register_callback_query_handler(lambda call: set_lucky_time_callback(call, bot),
                                       lambda c: c.data == "admin_lucky_time", state="*")
    dp.register_callback_query_handler(set_project_balance_start, lambda c: c.data == "admin_set_balance", state="*")
    dp.register_message_handler(set_project_balance_input, state=ProjectBalanceState.waiting_for_balance)
    dp.register_callback_query_handler(reset_balances_callback, lambda c: c.data == "obnylenie", state="*")
    dp.register_callback_query_handler(lambda call: confirm_reset_balances_callback(call, bot, app),
                                       lambda c: c.data == "confirm_reset_balances", state="*")
    dp.register_callback_query_handler(give_stars_start, lambda c: c.data == "dobavlenie", state="*")
    dp.register_message_handler(lambda msg, state: give_stars_input(msg, state, bot, app), state=GiveStarsState.amount)
    dp.register_callback_query_handler(db_management_menu, lambda c: c.data == "admin_db", state="*")
    dp.register_callback_query_handler(lambda call: handle_db_export(call, bot),
                                       lambda c: c.data in ["full_db", "usernames_list", "ids_list"], state="*")
    dp.register_callback_query_handler(generate_special_link, lambda c: c.data == "gen_link", state="*")
    dp.register_message_handler(lambda msg: manual_activity_check(msg, bot), commands=['ac'], state="*")
    dp.register_callback_query_handler(show_daily_gift_selection, lambda c: c.data == "admin_select_daily_gift",
                                       state="*")
    dp.register_callback_query_handler(lambda call: handle_set_daily_gift(call, bot, app),
                                       lambda c: c.data.startswith("set_daily_gift:"), state="*")
    dp.register_callback_query_handler(lambda call: toggle_withdrawals_callback(call, bot, app),
                                       lambda c: c.data == "toggle_withdrawals", state="*")
    dp.register_callback_query_handler(lambda call: toggle_referrals_callback(call, bot, app),
                                       lambda c: c.data == "toggle_referrals", state="*")
    register_admin_direct_message_handlers(dp, bot)
    log.info("Admin other handlers (including direct message) registered.")
