from typing import Any, Callable, Awaitable
from aiogram.types import TelegramObject, CallbackQuery, Message
from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy import select
from database.queries import UserQueries
from database.models import User
from cachetools import TTLCache
from config.config import settings
from keyboards.inline import sub_channel_kb

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker) -> None:
        super().__init__()
        self.session_pool = session_pool

    async def __call__(
            self, 
            handler: Callable[[TelegramObject, dict[str,Any]], Awaitable[Any]],
            event: TelegramObject, 
            data: dict[str, Any],) -> Any:
        
        async with self.session_pool() as session:
            #кладем сессию в словарь
            data['session'] = session

            #проверяем находится ли пользователь в бане
            user_event = data.get("event_from_user")

            if user_event:
                is_banned = await session.scalar(select(User.is_banned).where(User.tg_id == user_event.id))

                if is_banned:
                    if isinstance(event, CallbackQuery):
                        await event.answer("⛔ Вы заблокированы в боте.", show_alert=True)
                    elif isinstance(event, Message):
                        await event.answer("⛔ Вы заблокированы в боте.")

                    return
                    
            #передаем данные на handler
            return await handler(event,data)

class UserDatabaseMiddleware(BaseMiddleware):
    async def __call__(
            self, 
            handler: Callable[[TelegramObject, dict[str,Any]], Awaitable[Any]],
            event: TelegramObject, 
            data: dict[str, Any],) -> Any:

        tg_user: User | None = data.get('event_from_user')

        if tg_user is None or tg_user.is_bot:
            return await handler(event,data)

        session: AsyncSession = data['session']

        data['user'] = await UserQueries.get_or_create_users(
            session=session,
            tg_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name
        )

        return await handler(event,data)


#защита от спама
class AntiFrod(BaseMiddleware):
    def __init__(self, limit: float = 0.5):
        #храним до 10_000 юзеров с лимитом = limit сек
        self.cache = TTLCache(maxsize=10_000, ttl=limit)

    async def __call__(
            self,
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any]) -> Any:

        user = data.get("event_from_user")

        if not user:
            return await handler(event, data)

        if user.id in self.cache:
            if isinstance(event, CallbackQuery):
                await event.answer("⚠️ Пожалуйста, не кликайте так часто!", show_alert=False)
            elif isinstance(event, Message):
                pass

            return

        self.cache[user.id] = True

        return await handler(event, data)

#проверка подписки на канал

class SubChannelCheck(BaseMiddleware):

    CHAT_ID = settings.CHANNEL_ID

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any]) -> Any:

        bot: Bot = data.get("bot")
        user = data.get("event_from_user")
    
        if not user or user.is_bot:
            return await handler(event, data)

        try:
            member = await bot.get_chat_member(chat_id=self.CHAT_ID, user_id=user.id)

        except TelegramAPIError:
            return await handler(event, data)

        if member.status in ["creator","administrator","member"]:
            return await handler(event, data)
        
        if isinstance(event, CallbackQuery):
            # Гасим загрузку на кнопке
            return await event.answer("❌ Вы ещё не подписались на канал!", show_alert=True)

        text = (
            "🔒 <b>Обязательная подписка</b>\n\n"
            "Чтобы пользоваться каталогом и оформлять покупки, "
            "подпишитесь на наш официальный канал.\n\n"
            "<blockquote>📢 <b>Там мы публикуем:</b>\n"
            "• Свежие завозы аккаунтов\n"
            "• Промокоды на пополнение\n"
            "• Важные обновления шопа</blockquote>\n\n"
            "<i>После подписки нажмите кнопку «Проверить» ниже 👇</i>"
        )

        await bot.send_message(
        chat_id=user.id,
        text=text,
        reply_markup=sub_channel_kb(),
        parse_mode="HTML")
        
        return