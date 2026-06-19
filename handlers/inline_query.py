# Содержимое файла: handlers/inline_query.py
import logging
from uuid import uuid4  # Для генерации ID результата

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineQuery, InputTextMessageContent, InlineQueryResultArticle

# Импорты из проекта
from settings import USER_BOT  # Для формирования текста

log = logging.getLogger('handlers.inline_query')


async def handle_inline_query(inline_query: InlineQuery, bot: Bot):
    """
    Обрабатывает инлайн-запрос, который приходит, когда пользователь
    нажимает кнопку "Отправить приглашение другу" и выбирает чат.
    """
    user_id = inline_query.from_user.id
    # Текст, который приходит в query, это ссылка, которую мы указали в switch_inline_query
    referral_link = inline_query.query

    log.debug(f"Received inline query from user {user_id} with query: {referral_link}")

    # Формируем результат для отправки в выбранный чат
    # Текст можно сделать более привлекательным
    result_text = f"🚀 Присоединяйся к боту @{USER_BOT} и зарабатывай звезды!\n\nМоя ссылка: {referral_link}"
    input_content = InputTextMessageContent(
        message_text=result_text,
        parse_mode="HTML",  # Можно использовать HTML для форматирования
        disable_web_page_preview=True  # Отключаем превью ссылки, если не нужно
    )

    # Создаем элемент результата
    # title и description - то, что пользователь увидит в списке выбора перед отправкой
    item = InlineQueryResultArticle(
        id=str(uuid4()),  # Уникальный ID для результата
        title=f"Отправить приглашение в @{USER_BOT}",
        description="Поделиться реферальной ссылкой",
        input_message_content=input_content,
        # Можно добавить кнопку к отправляемому сообщению, если нужно
        # reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("Перейти к боту", url=referral_link))
    )

    # Отвечаем на инлайн-запрос
    try:
        # cache_time=1 - не кешировать результат надолго, чтобы ссылка всегда была актуальной (хотя она и так статична для юзера)
        await bot.answer_inline_query(inline_query.id, results=[item], cache_time=1)
        log.info(f"Answered inline query {inline_query.id} for user {user_id}")
    except Exception as e:
        log.error(f"Failed to answer inline query {inline_query.id} for user {user_id}: {e}")


def register_inline_handler(dp: Dispatcher, bot: Bot):
    """Регистрирует обработчик инлайн-запросов."""
    # Регистрируем хендлер без фильтров по тексту, т.к. он срабатывает только по switch_inline_query
    dp.register_inline_handler(lambda query: handle_inline_query(query, bot))
    log.info("Inline query handler registered.")
