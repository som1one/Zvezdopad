# Содержимое файла: handlers/admin_broadcast.py (Адаптировано для asyncpg)
import logging
import asyncio
import time

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import BotBlocked, ChatNotFound, UserDeactivated, TelegramAPIError, MessageNotModified

import database  # Наш async database
from settings import ADMIN_IDS
from utils import t
from keyboards import create_admin_cancel_markup, create_broadcast_confirmation_markup, \
    create_broadcast_progress_markup, create_hide_message_markup
from states import BroadcastState

log = logging.getLogger('handlers.admin_broadcast')

is_broadcasting = False


async def broadcast_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    markup = create_admin_cancel_markup(callback_data="cancell_ras")
    await call.message.edit_text(t(call.from_user.id, 'enter_mailing_text'), reply_markup=markup)
    await state.finish()
    await BroadcastState.waiting_for_message.set()
    log.info(f"Admin {call.from_user.id} started broadcast setup.")


async def broadcast_message_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup(callback_data="cancell_ras")

    if message.photo:
        photo_id = message.photo[-1].file_id
        text = message.caption or ""
        await state.update_data(broadcast_photo=photo_id, broadcast_text=text)
        log.debug(f"Broadcast message received (photo): photo_id={photo_id}, caption='{text}'")
    elif message.text:
        text = message.html_text
        await state.update_data(broadcast_photo=None, broadcast_text=text)
        log.debug(f"Broadcast message received (text): text='{text}'")
    else:
        await message.reply("❌ Пожалуйста, отправьте текст или фото с текстом.", reply_markup=markup);
        return

    await message.answer("Введите текст для первой Inline кнопки (или 'skip'/'пропустить'):", reply_markup=markup)
    await BroadcastState.waiting_for_button_text.set()


async def broadcast_button_text_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    button_text = message.text.strip()
    markup = create_admin_cancel_markup(callback_data="cancell_ras")

    if button_text.lower() in ['skip', 'пропустить']:
        data = await state.get_data()
        if not data.get('buttons'):
            await state.update_data(buttons=[])
            await preview_broadcast(message, state)  # await
            return
        else:
            await preview_broadcast(message, state)  # await
            return

    await state.update_data(current_button_text=button_text)
    await message.answer("Теперь введите URL для этой кнопки:", reply_markup=markup)
    await BroadcastState.waiting_for_button_url.set()


async def broadcast_button_url_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    button_url = message.text.strip()
    markup = create_admin_cancel_markup(callback_data="cancell_ras")
    data = await state.get_data()
    current_button_text = data.get('current_button_text')

    if not current_button_text:
        await message.reply("❗ Ошибка: не найден текст для кнопки.", reply_markup=markup);
        await state.finish();
        return

    if not (button_url.startswith('http://') or button_url.startswith('https://') or button_url.startswith('tg://')):
        await message.reply("❌ URL должен начинаться с http://, https:// или tg://", reply_markup=markup);
        return

    buttons = data.get('buttons', [])
    buttons.append({'text': current_button_text, 'url': button_url})
    await state.update_data(buttons=buttons, current_button_text=None)
    log.debug(f"Added broadcast button: text='{current_button_text}', url='{button_url}'")

    await message.answer("Кнопка добавлена. Хотите добавить еще одну? (Да/Нет)", reply_markup=markup)
    await BroadcastState.waiting_for_more_buttons.set()


async def broadcast_add_more_buttons_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup(callback_data="cancell_ras")

    if message.text.strip().lower() == 'да':
        await message.answer("Введите текст для следующей Inline кнопки:", reply_markup=markup)
        await BroadcastState.waiting_for_button_text.set()
    else:
        await preview_broadcast(message, state)  # await


async def preview_broadcast(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return

    data = await state.get_data()
    text = data.get('broadcast_text', 'Текст отсутствует')
    photo = data.get('broadcast_photo')
    buttons_data = data.get('buttons', [])
    bot_instance = message.bot

    preview_keyboard = InlineKeyboardMarkup()
    if buttons_data:
        for btn in buttons_data:
            if btn.get('text') and btn.get('url'):
                preview_keyboard.add(InlineKeyboardButton(text=btn['text'], url=btn['url']))
    preview_keyboard.add(InlineKeyboardButton("❌ Скрыть предпросмотр", callback_data=f"hide_preview"))

    try:
        if photo:
            await bot_instance.send_photo(admin_id, photo, caption=text, parse_mode='HTML',
                                          reply_markup=preview_keyboard)
        else:
            await bot_instance.send_message(admin_id, text, parse_mode='HTML', reply_markup=preview_keyboard,
                                            disable_web_page_preview=True)
    except Exception as e:
        log.error(f"Failed to send broadcast preview to admin {admin_id}: {e}")
        await message.answer(f"❌ Не удалось отправить предпросмотр: {e}");
        return

    confirm_keyboard = create_broadcast_confirmation_markup()
    await message.answer("☝️ Сообщение для рассылки.\nОтправляем всем?", reply_markup=confirm_keyboard)
    await BroadcastState.waiting_for_confirmation.set()


async def handle_broadcast_confirmation(call: CallbackQuery, state: FSMContext, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    await call.answer()

    if call.data == "confirm_broadcast":
        log.info(f"Admin {admin_id} confirmed broadcast.")
        await call.message.edit_text("✅ Рассылка подтверждена. Запускаю...")
        await finalize_broadcast(call.message, state, bot)  # await
    elif call.data == "edit_broadcast":
        log.info(f"Admin {admin_id} chose to edit broadcast.")
        markup = create_admin_cancel_markup(callback_data="cancell_ras")
        await call.message.edit_text("✏️ Настройка сброшена. Введите новый текст/фото:", reply_markup=markup)
        await state.finish()
        await BroadcastState.waiting_for_message.set()


# send_broadcast_message остается в основном без изменений, т.к. не работает с БД напрямую
async def send_broadcast_message(user_id: int, text: str, photo: str | None, buttons_data: list, bot: Bot):
    markup = InlineKeyboardMarkup()
    if buttons_data:
        for btn in buttons_data:
            if btn.get('text') and btn.get('url'):
                markup.add(InlineKeyboardButton(text=btn['text'], url=btn['url']))
    markup.add(create_hide_message_markup(user_id))

    try:
        if photo:
            await bot.send_photo(user_id, photo, caption=text, parse_mode="HTML", reply_markup=markup)
        else:
            await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        return "success"
    except (BotBlocked, UserDeactivated):
        log.warning(f"Broadcast failed {user_id}: Bot blocked/deactivated."); return "blocked"
    except ChatNotFound:
        log.warning(f"Broadcast failed {user_id}: Chat not found."); return "deleted"
    except TelegramAPIError as e:
        log.error(f"Broadcast failed {user_id} TelegramAPIError: {e}"); return "failed"
    except Exception as e:
        log.exception(f"Unexpected error sending broadcast to {user_id}: {e}"); return "failed"


async def finalize_broadcast(message: types.Message, state: FSMContext, bot: Bot):
    global is_broadcasting
    admin_id = message.chat.id
    if admin_id not in ADMIN_IDS: await state.finish(); return

    if is_broadcasting: await message.answer("⚠️ Другая рассылка уже запущена."); return

    is_broadcasting = True
    log.info(f"Admin {admin_id} initiated broadcast.")

    data = await state.get_data()
    text = data.get('broadcast_text')
    photo = data.get('broadcast_photo')
    buttons_data = data.get('buttons', [])

    if not text and not photo:
        await message.answer("❌ Нет текста или фото для рассылки.")
        is_broadcasting = False;
        await state.finish();
        return

    users_list = await database.get_users()  # await
    total_users = len(users_list)
    log.info(f"Starting broadcast to {total_users} users.")

    progress_markup = create_broadcast_progress_markup()
    try:
        progress_message = await bot.send_message(admin_id, f"🚀 Рассылка начата...\nВсего: {total_users}",
                                                  reply_markup=progress_markup)
    except Exception as e:
        log.error(
            f"Failed send initial progress msg admin {admin_id}: {e}"); is_broadcasting = False; await state.finish(); return

    counter, blocked, deleted, failed = 0, 0, 0, 0
    start_time = time.time()
    last_update_time = start_time
    batch_size = 25
    delay_between_messages = 0.04  # Задержка между сообщениями в батче не нужна, только между батчами

    for i in range(0, total_users, batch_size):
        if not is_broadcasting:
            log.warning(f"Broadcast stopped by admin {admin_id}.")
            try:
                await progress_message.edit_text("⚠️ Рассылка остановлена администратором.")
            except:
                pass
            break

        tasks = [send_broadcast_message(uid, text, photo, buttons_data, bot) for uid in users_list[i:i + batch_size]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                failed += 1; log.error(f"Exception during broadcast batch: {res}")
            elif res == "success":
                counter += 1
            elif res == "blocked":
                blocked += 1
            elif res == "deleted":
                deleted += 1
            elif res == "failed":
                failed += 1

        current_time = time.time()
        total_processed = i + len(users_list[i:i + batch_size])
        if current_time - last_update_time > 5 or total_processed >= total_users:
            percentage = int((total_processed / total_users) * 100) if total_users else 0
            progress_bar = "🟩" * (percentage // 10) + "⬜" * (10 - percentage // 10)
            elapsed_time = current_time - start_time
            speed = round(total_processed / elapsed_time, 1) if elapsed_time > 0 else 0
            progress_text = (
                f"<b>Прогресс:</b>\n{progress_bar} {percentage}%\n"
                f"Отправлено: {total_processed}/{total_users}\n\n"
                f"✅Успешно: <code>{counter}</code> | 🚫Блок: <code>{blocked}</code>\n"
                f"🗑Удален: <code>{deleted}</code> | ❌Ошибка: <code>{failed}</code>\n\n"
                f"⏳Время: {int(elapsed_time)} сек | ⚡️Скорость: {speed}/сек"
            )
            try:
                await progress_message.edit_text(progress_text, reply_markup=progress_markup, parse_mode="HTML")
            except MessageNotModified:
                pass
            except Exception as e:
                log.error(f"Failed update progress message: {e}")
            last_update_time = current_time

        await asyncio.sleep(1.0)  # Задержка между БАТЧАМИ в 1 секунду

    is_broadcasting = False
    await state.finish()

    final_stats_text = (
        f"<b>🎉 Рассылка завершена!</b>\n\n"
        f"Всего обработано: {total_users}\n"
        f"✅ Успешно: <code>{counter}</code>\n"
        f"🚫 Блок: <code>{blocked}</code>\n"
        f"🗑 Удален: <code>{deleted}</code>\n"
        f"❌ Ошибка: <code>{failed}</code>\n\n"
        f"⏱ Общее время: {int(time.time() - start_time)} сек."
    )
    try:
        await progress_message.delete()
    except:
        pass
    markup = create_admin_cancel_markup()
    await bot.send_message(admin_id, final_stats_text, reply_markup=markup, parse_mode="HTML")


async def stop_broadcast_callback(call: CallbackQuery, state: FSMContext):
    global is_broadcasting
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer()

    if is_broadcasting:
        is_broadcasting = False
        log.warning(f"Broadcast stop requested by admin {admin_id}")
        await call.message.edit_text("⏳ Останавливаю рассылку...")
    else:
        await call.message.edit_text("ℹ️ Активной рассылки нет.")

    markup = create_admin_cancel_markup()
    await call.message.answer("Выберите действие:", reply_markup=markup)


async def cancel_broadcast_callback(call: CallbackQuery, state: FSMContext):
    global is_broadcasting
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer("Отмена действия")

    is_broadcasting = False
    current_state = await state.get_state()
    if current_state is not None:
        log.info(f"Admin {admin_id} cancelled broadcast setup at state {current_state}")
        await state.finish()

    markup = create_admin_cancel_markup()
    try:
        await call.message.edit_text("Действие отменено.", reply_markup=markup)
    except:
        await call.message.answer("Действие отменено.", reply_markup=markup)


def register_admin_broadcast_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(broadcast_start, lambda c: c.data == "admin_mailing", state="*")
    dp.register_callback_query_handler(cancel_broadcast_callback, lambda c: c.data == "cancell_ras",
                                       state=BroadcastState.all_states)
    dp.register_message_handler(broadcast_message_input, state=BroadcastState.waiting_for_message,
                                content_types=[types.ContentType.TEXT, types.ContentType.PHOTO])
    dp.register_message_handler(broadcast_button_text_input, state=BroadcastState.waiting_for_button_text)
    dp.register_message_handler(broadcast_button_url_input, state=BroadcastState.waiting_for_button_url)
    dp.register_message_handler(broadcast_add_more_buttons_input, state=BroadcastState.waiting_for_more_buttons)
    dp.register_callback_query_handler(lambda call, state: handle_broadcast_confirmation(call, state, bot),
                                       lambda c: c.data in ["confirm_broadcast", "edit_broadcast"],
                                       state=BroadcastState.waiting_for_confirmation)
    dp.register_callback_query_handler(stop_broadcast_callback, lambda c: c.data == "stop_broadcast", state="*")
    log.info("Admin broadcast handlers registered.")
