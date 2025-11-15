import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from .config import settings
from .db import init_db
from .handlers import router
from .scheduler import scheduler_loop


async def main():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан в .env")

    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()
    dp.include_router(router)

    asyncio.create_task(scheduler_loop(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
