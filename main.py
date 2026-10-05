import asyncio
import logging
import os
import sqlite3
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    Message,
    WebAppInfo,
    MenuButtonWebApp,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ======================= НАСТРОЙКИ =======================
# Токен лучше хранить в переменной окружения BOT_TOKEN.
# Можно временно вставить прямо сюда: BOT_TOKEN = "8691327822:AAHREP1hlS96J0IHipMrXbUE0Lk9j316Tsg"
BOT_TOKEN = os.getenv("BOT_TOKEN", "8691327822:AAHREP1hlS96J0IHipMrXbUE0Lk9j316Tsg")

# Адрес игры на GitHub Pages.
# WEBAPP_FILE — точное имя html-файла, который лежит в репозитории.
WEBAPP_BASE = "https://8o8o99oooooo-gif.github.io/burmaldaCasino/"
WEBAPP_FILE = "crash_purple_fixed.html"
# Меняй цифру при каждом обновлении игры, чтобы Телеграм не брал файл из кэша.
WEBAPP_VERSION = "2"

WEBAPP_URL = f"{WEBAPP_BASE}{WEBAPP_FILE}?v={WEBAPP_VERSION}"

START_BALANCE = 1000          # стартовый баланс нового игрока
DAILY_BONUS = 500             # сумма ежедневного бонуса
DAILY_COOLDOWN = 24 * 60 * 60  # раз в 24 часа (в секундах)

DB_PATH = "bot.db"
# =========================================================

logging.basicConfig(level=logging.INFO)
router = Router()


# ---------------------- база данных ----------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER NOT NULL DEFAULT 0,
                last_bonus INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def get_user(user_id: int, username: str | None = None) -> sqlite3.Row:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)",
                (user_id, username, START_BALANCE),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        elif username and row["username"] != username:
            conn.execute(
                "UPDATE users SET username = ? WHERE user_id = ?",
                (username, user_id),
            )
        return row


def add_balance(user_id: int, amount: int):
    with db() as conn:
        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )


def set_last_bonus(user_id: int, ts: int):
    with db() as conn:
        conn.execute(
            "UPDATE users SET last_bonus = ? WHERE user_id = ?", (ts, user_id)
        )


# ---------------------- клавиатуры -----------------------
def main_menu_kb(balance: int):
    builder = InlineKeyboardBuilder()
    builder.button(text=f"💰 Баланс: {balance}", callback_data="menu_balance")
    builder.button(text="🎮 Играть", callback_data="menu_games")
    builder.button(text="🎁 Ежедневный бонус", callback_data="menu_bonus")
    builder.button(text="🌐 Казино (Web App)", web_app=WebAppInfo(url=WEBAPP_URL))
    builder.adjust(1)
    return builder.as_markup()


def back_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В меню", callback_data="menu_main")
    return builder.as_markup()


def games_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 Открыть казино", web_app=WebAppInfo(url=WEBAPP_URL))
    builder.button(text="⬅️ В меню", callback_data="menu_main")
    builder.adjust(1)
    return builder.as_markup()


def menu_text(name: str) -> str:
    return (
        f"👋 Привет, <b>{name}</b>!\n\n"
        "Добро пожаловать в <b>Burmaldinka Casino</b>.\n"
        "Выбери действие:"
    )


# ---------------------- хендлеры -------------------------
@router.message(CommandStart())
async def cmd_start(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    await message.answer(
        menu_text(message.from_user.full_name),
        reply_markup=main_menu_kb(user["balance"]),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    await message.answer(
        menu_text(message.from_user.full_name),
        reply_markup=main_menu_kb(user["balance"]),
    )


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = get_user(message.from_user.id, message.from_user.username)
    await message.answer(f"💰 Твой баланс: <b>{user['balance']}</b>")


@router.callback_query(F.data == "menu_main")
async def cb_main(call: CallbackQuery):
    user = get_user(call.from_user.id, call.from_user.username)
    await call.message.edit_text(
        menu_text(call.from_user.full_name),
        reply_markup=main_menu_kb(user["balance"]),
    )
    await call.answer()


@router.callback_query(F.data == "menu_balance")
async def cb_balance(call: CallbackQuery):
    user = get_user(call.from_user.id, call.from_user.username)
    await call.answer(f"💰 Баланс: {user['balance']}", show_alert=True)


@router.callback_query(F.data == "menu_games")
async def cb_games(call: CallbackQuery):
    await call.message.edit_text(
        "🎮 <b>Игры</b>\n\n"
        "Кейсы, апгрейд, контракты, краш, плинко, лесенка и сапёр "
        "находятся в казино. Нажми кнопку ниже:",
        reply_markup=games_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "menu_bonus")
async def cb_bonus(call: CallbackQuery):
    user = get_user(call.from_user.id, call.from_user.username)
    now = int(time.time())
    left = user["last_bonus"] + DAILY_COOLDOWN - now

    if left > 0:
        hours, rest = divmod(left, 3600)
        minutes = rest // 60
        text = (
            "🎁 <b>Ежедневный бонус</b>\n\n"
            f"Ты уже забирал бонус. Следующий через <b>{hours} ч {minutes} мин</b>."
        )
    else:
        add_balance(call.from_user.id, DAILY_BONUS)
        set_last_bonus(call.from_user.id, now)
        new_balance = user["balance"] + DAILY_BONUS
        text = (
            "🎁 <b>Ежедневный бонус</b>\n\n"
            f"Тебе начислено <b>+{DAILY_BONUS}</b>!\n"
            f"💰 Баланс: <b>{new_balance}</b>"
        )

    await call.message.edit_text(text, reply_markup=back_kb())
    await call.answer()


# ---------------------- запуск ---------------------------
async def main():
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    # Кнопка Web App рядом с полем ввода (меню бота)
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="🎰 Казино", web_app=WebAppInfo(url=WEBAPP_URL)
            )
        )
    except Exception as e:
        logging.warning("Не удалось поставить кнопку меню: %s", e)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
