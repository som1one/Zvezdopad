# В файле handlers/admin_limits.py
import logging
from aiogram import types, Bot, Dispatcher
from aiogram.types import CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified, InvalidQueryID

import database
from settings import ADMIN_IDS
from utils import t
from keyboards import create_admin_limits_menu, create_admin_limits_cancel_markup
from states import AdminLimitsState

log = logging.getLogger('handlers.admin_limits')

# --- ИСПРАВЛЕНИЕ ОПЕЧАТКИ ЗДЕСЬ ---
LIMIT_CONFIG = {
    "wheel_referral_req": {
        "state": AdminLimitsState.waiting_for_wheel_ref_req, "prompt_key": "ask_new_limit_wheel_ref",
        "name": "Реф. Колесо", "getter": database.get_wheel_referral_req
    },
    "wheel_daily_limit": {
        "state": AdminLimitsState.waiting_for_wheel_daily_limit, "prompt_key": "ask_new_limit_wheel_daily",
        "name": "Лимит Колесо/день", "getter": database.get_wheel_daily_limit
    },
    "exchange_referral_req": {
        "state": AdminLimitsState.waiting_for_exchange_referral_req, "prompt_key": "ask_new_limit_exchange_ref",
        "name": "Реф. Обмен", "getter": database.get_exchange_referral_req
    },
    "exchange_daily_limit": {
        "state": AdminLimitsState.waiting_for_exchange_daily_limit, "prompt_key": "ask_new_limit_exchange_daily",
        "name": "Лимит Обмен/день", "getter": database.get_exchange_daily_limit
    },
    "streak_days_required": {
        "state": AdminLimitsState.waiting_for_streak_days_required, "prompt_key": "ask_new_streak_days",
        "name": "🔥 Огонёк (дней)", "getter": database.get_streak_days_required
    },
    "streak_reward": {
        "state": AdminLimitsState.waiting_for_streak_reward, "prompt_key": "ask_new_streak_reward",
        "name": "🔥 Огонёк (награда ⭐)", "getter": database.get_streak_reward, "is_float": True
    },
}


# --- КОНЕЦ ИСПРАВЛЕНИЯ ---


async def show_limits_menu(
        event: types.Message | types.CallbackQuery | None,
        user_id: int,
        chat_id: int | None = None,
        bot_instance: Bot | None = None
):
    target_message = None
    is_callback = False

    # Определяем источник вызова и получаем необходимые объекты
    if isinstance(event, types.CallbackQuery):
        target_message = event.message
        bot_instance = event.bot
        chat_id = target_message.chat.id
        if user_id not in ADMIN_IDS: await event.answer("Нет доступа.", show_alert=True); return
        try:
            await event.answer()
        except InvalidQueryID:
            log.warning(f"IQID fail show_limits_menu user {user_id}");
            return
        is_callback = True
    elif isinstance(event, types.Message):
        target_message = event
        bot_instance = event.bot
        chat_id = target_message.chat.id
        if user_id not in ADMIN_IDS: return
    elif chat_id and bot_instance:
        pass  # Используем переданные chat_id и bot_instance
    else:
        log.error(
            f"show_limits_menu called with insufficient arguments: event={event}, user_id={user_id}, chat_id={chat_id}, bot={bot_instance}");
        return

    if not user_id: log.error(f"show_limits_menu called without user_id"); return
    if not bot_instance: log.error(f"show_limits_menu failed get bot instance user {user_id}"); return
    if not chat_id: log.error(f"show_limits_menu failed get chat_id user {user_id}"); return

    log.debug(f"Showing limits menu for admin {user_id}")  # Лог
    markup = await create_admin_limits_menu(
        wheel_ref_req=await database.get_wheel_referral_req(),
        wheel_daily_limit=await database.get_wheel_daily_limit(),
        exchange_ref_req=await database.get_exchange_referral_req(),
        exchange_daily_limit=await database.get_exchange_daily_limit(),
        streak_days=await database.get_streak_days_required(),
        streak_reward=await database.get_streak_reward()
    )
    text = t(user_id, 'admin_limits_menu_title')

    try:
        if is_callback and target_message:
            await target_message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        else:
            await bot_instance.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
    except MessageNotModified:
        pass
    except Exception as e:
        log.error(f"Failed to edit/send limits menu for admin {user_id}: {e}")
        if event:  # Fallback только если был event
            try:
                await bot_instance.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
            except Exception as fallback_e:
                log.error(f"Failed send fallback limits menu for admin {user_id}: {fallback_e}")


async def edit_limit_start(call: CallbackQuery, state: FSMContext):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer()

    try:
        limit_key = call.data.split(":")[1]
        if limit_key not in LIMIT_CONFIG: raise ValueError("Unknown limit key")

        config = LIMIT_CONFIG[limit_key]
        await state.update_data(limit_key_to_edit=limit_key)
        await config["state"].set()

        current_value = await config["getter"]()
        prompt = t(admin_id, config["prompt_key"]) + f"\n\nТекущее значение: <code>{current_value}</code>"
        markup = create_admin_limits_cancel_markup()
        log.info(f"Admin {admin_id} starts editing limit '{limit_key}'. Current value: {current_value}")  # Лог

        await call.message.edit_text(prompt, reply_markup=markup, parse_mode="HTML")

    except (IndexError, ValueError) as e:
        log.error(f"Error parsing edit_limit callback: {call.data} - {e}")
        await call.answer("Ошибка данных.", show_alert=True);
        await state.finish()
    except Exception as e:
        log.exception(f"Error starting limit edit key from {call.data}: {e}")
        await call.answer("Ошибка при запуске.", show_alert=True);
        await state.finish()


async def process_limit_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    chat_id = message.chat.id
    bot_instance = message.bot
    if admin_id not in ADMIN_IDS: await state.finish(); return

    state_data = await state.get_data()
    limit_key = state_data.get("limit_key_to_edit")
    markup = create_admin_limits_cancel_markup()

    if not limit_key or limit_key not in LIMIT_CONFIG:
        log.error(f"Invalid state or limit_key '{limit_key}' admin {admin_id} processing limit input.")
        await message.reply("Ошибка состояния. Попробуйте снова.", reply_markup=markup);
        await state.finish();
        return

    config = LIMIT_CONFIG[limit_key]
    log.info(f"Admin {admin_id} entered new value for limit '{limit_key}': {message.text}")  # Лог

    try:
        # streak_reward принимает дробные значения
        if config.get("is_float"):
            new_value = float(message.text.strip())
        else:
            new_value = int(message.text.strip())
        if new_value < 0: raise ValueError("Value cannot be negative")

        await database.set_config_value(limit_key, new_value)
        log.info(f"Admin {admin_id} successfully updated limit '{limit_key}' to {new_value}")

        display_value = f"{new_value:.1f}" if isinstance(new_value, float) else str(new_value)
        success_text = t(admin_id, 'limit_updated_success').format(limit_name=config["name"], value=display_value)
        await message.answer(success_text)  # Отправляем сообщение об успехе

        await state.finish()  # Завершаем состояние
        # Показываем обновленное меню лимитов
        await show_limits_menu(event=None, user_id=admin_id, chat_id=chat_id, bot_instance=bot_instance)

    except ValueError:
        log.warning(f"Admin {admin_id} entered invalid value for limit '{limit_key}': {message.text}")  # Лог
        await message.reply(t(admin_id, 'invalid_limit_value'), reply_markup=markup)
        # Состояние НЕ завершаем, даем исправить
    except Exception as e:
        log.exception(f"Error updating limit '{limit_key}' admin {admin_id}: {e}")
        await message.reply(t(admin_id, 'error_updating_limit'), reply_markup=markup);
        await state.finish()  # Завершаем при ошибке


async def cancel_limit_edit(call: CallbackQuery, state: FSMContext):
    admin_id = call.from_user.id
    log.info(f"Admin {admin_id} cancelled limit editing.")  # Лог
    await call.answer("Отмена")
    await state.finish()
    # Показываем меню лимитов после отмены
    await show_limits_menu(call, admin_id)


def register_admin_limits_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(lambda call: show_limits_menu(call, call.from_user.id),
                                       lambda c: c.data == "admin_limits_menu", state="*")
    dp.register_callback_query_handler(edit_limit_start, lambda c: c.data.startswith("edit_limit:"), state="*")
    dp.register_message_handler(process_limit_input, state=AdminLimitsState.all_states)
    # Используем lambda для передачи state в cancel_limit_edit, хотя он там не нужен напрямую
    dp.register_callback_query_handler(lambda call, state: cancel_limit_edit(call, state),
                                       lambda c: c.data == "admin_limits_menu",  # Отмена возвращает в меню
                                       state=AdminLimitsState.all_states)
    log.info("Admin limits management handlers registered.")
