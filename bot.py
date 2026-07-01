"""
Печенько — Telegram-бот на базе Google Gemini API.

Поддерживает:
1. Inline-режим — можно вызвать в ЛЮБОМ чате, даже там, где бота нет:
   просто напиши в любом чате "@Pechennko_bot твой вопрос"
2. Обычный режим — личные сообщения и упоминания в группах (@Pechennko_bot ...)
3. Настраиваемый системный промт (меняется в config.py или через /setprompt для владельца)

Автор запуска: настрой .env, поставь зависимости из requirements.txt и запусти.
"""

import logging
import os
import uuid

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    InlineQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import google.generativeai as genai

from config import (
    TELEGRAM_BOT_TOKEN,
    GEMINI_API_KEY,
    DEFAULT_SYSTEM_PROMPT,
    GEMINI_MODEL,
    OWNER_ID,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Храним текущий системный промт в памяти. Можно сменить командой /setprompt.
# При перезапуске бота сбросится на DEFAULT_SYSTEM_PROMPT из config.py.
current_system_prompt = {"text": DEFAULT_SYSTEM_PROMPT}

genai.configure(api_key=GEMINI_API_KEY)


def build_model():
    """Создаёт модель ??? с текущим системным промтом."""
    return genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=current_system_prompt["text"],
    )


async def ask_gemini(user_text: str) -> str:
    """Отправляет запрос в ??? и возвращает текст ответа."""
    try:
        model = build_model()
        response = await model.generate_content_async(user_text)
        return response.text.strip()
    except Exception as e:
        logger.exception("Ошибка при запросе к ???")
        return f"Упс, что-то пошло не так: {e}"


# ---------- ОБЫЧНЫЙ РЕЖИМ (личка + группы) ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я Печенько 👋\n\n"
        "Пиши мне в личку — отвечу.\n"
        "В группе — упомяни меня (@Pechennko_bot вопрос) или ответь на моё сообщение.\n"
        "А ещё меня можно вызвать в ЛЮБОМ чате: напиши там '@Pechennko_bot вопрос'."
    )


async def setprompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для владельца бота — меняет системный промт на лету."""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Эта команда доступна только владельцу бота.")
        return

    new_prompt = " ".join(context.args)
    if not new_prompt:
        await update.message.reply_text(
            "Использование: /setprompt текст нового системного промта\n\n"
            f"Текущий промт:\n{current_system_prompt['text']}"
        )
        return

    current_system_prompt["text"] = new_prompt
    await update.message.reply_text("Системный промт обновлён ✅")


async def getprompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Текущий системный промт:\n\n{current_system_prompt['text']}"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отвечает в личных сообщениях всегда, а в группах — только если бота
    упомянули (@Pechennko_bot) или ответили на его сообщение."""
    message = update.message
    if message is None or message.text is None:
        return

    chat_type = message.chat.type
    bot_username = context.bot.username

    text = message.text
    is_mentioned = f"@{bot_username}" in text
    is_reply_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == context.bot.id
    )

    if chat_type in ("group", "supergroup"):
        if not (is_mentioned or is_reply_to_bot):
            return
        text = text.replace(f"@{bot_username}", "").strip()

    if not text:
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    answer = await ask_gemini(text)
    await message.reply_text(answer)


# ---------- INLINE-РЕЖИМ (вызов в любом чате без добавления бота) ----------

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query

    if not query:
        return

    answer = await ask_gemini(query)

    # Telegram ограничивает длину превью и текста результата
    preview = answer if len(answer) <= 200 else answer[:197] + "..."

    results = [
        InlineQueryResultArticle(
            id=str(uuid.uuid4()),
            title="Ответ Печенько",
            description=preview,
            input_message_content=InputTextMessageContent(answer[:4096]),
        )
    ]

    await update.inline_query.answer(results, cache_time=1, is_personal=True)


def main():
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        raise RuntimeError(
            "Задай TELEGRAM_BOT_TOKEN и апи кей в .env файле (см. .env.example)"
        )

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setprompt", setprompt))
    app.add_handler(CommandHandler("getprompt", getprompt))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
