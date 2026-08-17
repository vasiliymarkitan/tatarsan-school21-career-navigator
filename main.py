import asyncio
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from db.database import init_db
from bot.handlers import router
from scheduler.digest import setup_scheduler, run_parser

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def main():
    print("🚀 Запускаю Карьерный Навигатор 21...")

    # Инициализируем БД
    await init_db()
    print("✅ База данных готова")

    # Создаём бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.include_router(router)

    # Запускаем планировщик
    setup_scheduler(bot)

    # Первый запуск парсера сразу при старте
    print("🔄 Первичный парсинг...")
    await run_parser()

    # Запускаем бота
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
