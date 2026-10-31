"""Telegram-бот партнёрской программы МФО (перенос с Puzzlebot).

Структура повторяет сценарий из конструктора:
  /start -> сообщение с картинкой и подписью, две кнопки:
            РОССИЯ     -> mini app https://zaim-deneg.ru/
            КАЗАХСТАН  -> mini app https://oformit-mikrokrediti-bistro.zaimstore.com/
  /broadcast <текст> -> рассылка по базе (только для админа).

Дожим через 10 минут появится позже, когда подключим базу пользователей.

Хостинг: botost.ru (long polling, токен берётся из BOT_TOKEN).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("mfo-bot")

# --- Настройки из переменных окружения (botost.ru подставляет BOT_TOKEN сам) ---

BOT_TOKEN = os.environ["BOT_TOKEN"].strip()

BROADCAST_ADMIN_ID = int(os.environ["BROADCAST_ADMIN_ID"].strip())

# Mini App по странам. Telegram требует HTTPS для Web App.
SITE_RU = os.getenv("SITE_RU_URL", "https://zaim-deneg.ru/").strip()
SITE_KZ = os.getenv(
    "SITE_KZ_URL",
    "https://oformit-mikrokrediti-bistro.zaimstore.com/",
).strip()

# Текст и картинка приветственного сообщения — как в конструкторе.
START_TEXT = os.getenv(
    "START_TEXT",
    "Нужны деньги? Подберите предложение для своей страны.\n\n"
    "Нажмите кнопку ниже — откроется каталог предложений.",
).strip()

START_IMAGE = Path(__file__).parent / os.getenv("START_IMAGE", "assets/start.png")

# База пока в памяти: переживает только жизнь процесса.
USERS: set[int] = set()


def countries_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="РОССИЯ",
                    web_app=WebAppInfo(url=SITE_RU),
                    callback_data="country_ru",
                )
            ],
            [
                InlineKeyboardButton(
                    text="КАЗАХСТАН",
                    web_app=WebAppInfo(url=SITE_KZ),
                    callback_data="country_kz",
                )
            ],
        ]
    )


dp = Dispatcher()


async def send_start(message: Message) -> None:
    if message.from_user:
        USERS.add(message.from_user.id)

    if START_IMAGE.is_file():
        await message.answer_photo(
            photo=FSInputFile(START_IMAGE),
            caption=START_TEXT,
            reply_markup=countries_keyboard(),
        )
    else:
        log.warning("Картинка не найдена: %s", START_IMAGE)
        await message.answer(START_TEXT, reply_markup=countries_keyboard())


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await send_start(message)


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Доступные команды:\n"
        "/start — начать заново\n"
        "/help — эта справка"
    )


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject) -> None:
    if not message.from_user or message.from_user.id != BROADCAST_ADMIN_ID:
        await message.answer("⛔ Эта команда доступна только администратору.")
        return

    text = (command.args or "").strip()
    if not text:
        await message.answer(
            "Напишите текст так:\n<code>/broadcast Текст сообщения</code>"
        )
        return

    if not USERS:
        await message.answer(
            "Пока нет сохранённых пользователей. Подключите базу, чтобы "
            "рассылка работала после перезапуска."
        )
        return

    sent = 0
    blocked = 0
    errors = 0
    total = len(USERS)

    status = await message.answer(f"⏳ Рассылка… 0/{total}")

    for idx, user_id in enumerate(list(USERS), start=1):
        try:
            await message.bot.send_message(user_id, text)
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
            USERS.discard(user_id)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            errors += 1
        except Exception:
            log.exception("Ошибка при отправке %s", user_id)
            errors += 1

        if idx % 25 == 0:
            await asyncio.sleep(1)  # не уходить в 429
            try:
                await status.edit_text(f"⏳ Рассылка… {idx}/{total}")
            except Exception:
                pass

    await status.edit_text(
        f"✅ Рассылка завершена.\n"
        f"Отправлено: {sent}\n"
        f"Заблокировали: {blocked}\n"
        f"Ошибок: {errors}"
    )


@dp.message()
async def fallback(message: Message) -> None:
    # Любой текст вне команд — снова показываем приветствие с кнопками.
    await send_start(message)


async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Если на токене остался webhook (например, от Puzzlebot), polling не
    # получит апдейты. Снимаем его при старте.
    await bot.delete_webhook(drop_pending_updates=True)

    log.info("Запуск polling…")
    await dp.start_polling(bot, allowed_updates=["message"])


if __name__ == "__main__":
    asyncio.run(main())
