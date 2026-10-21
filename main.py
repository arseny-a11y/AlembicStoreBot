from aiogram import Dispatcher, Bot
from aiogram.client.session.aiohttp import AiohttpSession # работа с proxy
import asyncio
import logging
from config.config import settings
from middlewares.middleware import DbSessionMiddleware, UserDatabaseMiddleware, AntiFrod, SubChannelCheck, MaintenanceMiddleware
from database.database import async_session_factory
from database.database import init_db
from handlers.user import user_router
from handlers.catalog import catalog_router
from handlers.admin import admin_router
from handlers.payments import router_pay

async def main():

    logging.basicConfig(level=logging.INFO)
    
    session = AiohttpSession(proxy=settings.PROXY_URL)
    bot = Bot(settings.TOKEN,session=session)
    dp = Dispatcher()

    
    #инициализируем табилицы в базе
    await init_db()

    #подключаем middlewares
    dp.update.outer_middleware(AntiFrod())

    # 2. Проверка режима техработ
    dp.update.outer_middleware(MaintenanceMiddleware())

    # 3. Работа с базой данных (открытие сессии и регистрация/получение юзера)
    dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
    dp.update.outer_middleware(UserDatabaseMiddleware())

    # 4. Проверка обязательной подписки на канал
    sub_channel = SubChannelCheck()
    user_router.message.middleware(sub_channel)
    user_router.callback_query.middleware(sub_channel)

    catalog_router.message.middleware(sub_channel)
    catalog_router.callback_query.middleware(sub_channel)

    #подключаем routers
    dp.include_routers(
        admin_router,
        router_pay,
        catalog_router,
        user_router,
    )

 
    try:
        print('Бот запущен!')
        # Удаляем вебхуки и сбрасываем подвисшие апдейты
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

    finally:
        # Корректно закрываем сессию соединений
        await bot.session.close()   

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print('Бот остановлен!')

    