from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message,InlineKeyboardButton,InlineKeyboardMarkup
from database.models import User, PromoCode,PromoUsage, Orders
from database.queries import UserQueries,check_promocode
from aiogram.types import FSInputFile #работа с изображениями
from keyboards.reply import create_keyboard_menu
from keyboards.inline import keyboard_support,keyboard_profile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from payments.crypto_pay import CryptoPay
from handlers.admin import ADMIN_IDS
from html import escape


user_router = Router()

@user_router.message(CommandStart())
async def start_command(message: Message, user: User):

    is_admin = message.from_user.id in ADMIN_IDS

    photo = FSInputFile('images/menu.png')

    text = (
        f"👋 <b>{message.from_user.first_name}</b>, приветствуем тебя!\n\n"
        "🎉 <b>Добро пожаловать в SUP SHOP!</b>\n"
        "У нас ты найдешь лучший выбор аккаунтов и цифровых товаров Supercell.\n\n"
        "😉 Заглядывай в каталог и выбирай самые топовые товары! С любовью, SUP SHOP 🧡"
    )
    await message.answer_photo(photo=photo,caption=text,parse_mode='HTML',reply_markup=create_keyboard_menu(is_admin))


#обработка информации о магазине
@user_router.message(F.text == "ℹ️ О SUP SHOP")
async def information_shop(message: Message):
    photo = FSInputFile('images/menu.png')

    text = (
        "👋 <b>Приветствуем в SUP SHOP!</b>\n\n"
        "❤️ Мы рады предложить вам широкий ассортимент товаров по конкурентным ценам. 🛍 Наша бизнес-модель основана на приобретении дорогостоящих материалов 💎 и их реализации по более доступным ценам 💰 благодаря работе с большой аудиторией. 👨‍👩‍👧‍👦\n\n"
        "📅 Дата основания магазина: 04.09.2026."
    )
    await message.answer_photo(photo=photo,caption=text,parse_mode='HTML')


#обработка запроса на контакты поддержки
@user_router.message(F.text == "🆘 Поддержка")
async def support_shop(message: Message):
    photo = FSInputFile('images/support.png')

    text = (
        "🤝 В нашем боте вы всегда можете рассчитывать на оперативную поддержку! Возникли вопросы при покупке, оплате или получении товара? Пишите нам! Мы ответим максимально быстро и решим вашу проблему\n\n"
        "🚨 Внимание! Мы никогда не пишем первыми. Если вам кто-то пишет от имени нашего бота или службы поддержки — это мошенники. Будьте осторожны!\n\n"
        "✍️ Связаться с поддержкой: @Gemaglobin"
    )
    await message.answer_photo(photo=photo,caption=text,reply_markup=keyboard_support())


#обработка запроса на статистику профиля
@user_router.message(F.text == "Профиль 👤")
async def user_profile(message: Message, user: User):
    photo = FSInputFile('images/profile.png')

    registered_at = user.registered_at.strftime("%d.%m.%Y")
    username = user.username if user.username else 'Отсутсвует'
    text = (
        f"📍<b>ID</b>: {user.tg_id}\n"
        f"💾 <b>Имя</b>: @{username}\n"
        f"💵 <b>Баланс</b>: {user.balance}\n"
        f"🕑 <b>Дата регистрации</b>: {registered_at}\n"
    )
    await message.answer_photo(photo=photo,caption=text,reply_markup=keyboard_profile(),parse_mode='HTML')

#активация промокода

class EnterPromoState(StatesGroup):
    waiting_for_code = State()

#отмена ввода промокода
@user_router.callback_query(F.data == "user_cancel_promocode", EnterPromoState.waiting_for_code)
async def enter_cancel_promocode(callback: CallbackQuery, state: FSMContext):
   await state.clear()
   await callback.message.edit_text("🚫 Ввод промокода отменен")
   await callback.answer()

@user_router.callback_query(F.data == "enter_promocode")
async def enter_promocode_handler(callback: CallbackQuery, state: FSMContext):

    await state.set_state(EnterPromoState.waiting_for_code)

    cancel_kb = InlineKeyboardMarkup(
    inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="user_cancel_promocode")]
        ]
    )

    await callback.message.answer("✨ Введите промокод: ", reply_markup=cancel_kb)
    await callback.answer()

@user_router.message(EnterPromoState.waiting_for_code)
async def waiting_for_code_state(message: Message, state: FSMContext, session: AsyncSession):

    cancel_kb = InlineKeyboardMarkup(
    inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="user_cancel_promocode")]
        ]
    )

    if not message.text:
        return await message.answer("⚠️ Отправьте промокод текстовым сообщением:")
    
    promo_code = message.text.strip().upper()

    existing = await check_promocode(session, promo_code)

    if existing is None or existing.max_uses <= 0:
        return await message.answer("❌ Промокод не найден, либо уже исчерпан. Попробуйте еще раз или нажмите отмену:",reply_markup=cancel_kb)

    user_id = message.from_user.id

    used_code = await session.scalar(select(PromoUsage).where(PromoUsage.promo_id == existing.id, PromoUsage.tg_id == user_id))

    if used_code:
        await state.clear()
        return await message.answer("⚠️ Вы уже активировали этот промокод!")

    user = await session.scalar(select(User).where(User.tg_id == user_id))

    if user is None:
        await state.clear()
        return await message.answer("❌ Пользовалель не найден в базе")

    
    existing.max_uses -= 1
    existing.current_uses += 1
    user.balance += existing.reward_amount


    create_promocode_usage = PromoUsage(
        promo_id=existing.id,
        tg_id=user_id
    )


    session.add(create_promocode_usage)
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ Промокод <code>{promo_code}</code> успешно активирован!\n\n"
        f"💰 Ваш баланс пополнен на <b>{existing.reward_amount:.2f} ₽</b>\n"
        f"🪙 Текущий баланс: <b>{user.balance:.2f} ₽</b>",
        parse_mode="HTML",
    )

#История покупок
@user_router.callback_query(F.data == "history_purchases")
async def history_purchases_handler(callback: CallbackQuery, session: AsyncSession):
    user_id = callback.from_user.id

    all_purchases = []
    query = (
        await session.scalars(
            select(Orders).
            where(Orders.user_id == user_id).
            order_by(Orders.id.desc()).
            limit(10)
        )
    ).all()

    if not query:
        return await callback.answer("У вас нет совершенных покупок.", show_alert=True)
        
    

    for count, q in enumerate(query, start=1):
        title = escape(q.name or "Товар")
        price = int(q.price)
        id = q.id

        raw_data = q.item_data or ""
        trimmed_data = raw_data[:200]
        safe_data = escape(trimmed_data)

        if len(raw_data) > 200:
            safe_data += "..."

        status_badge = " [ ↩️ ВОЗВРАТ ]" if q.refund else ""
        all_purchases.append(
            f"ID #{id}{status_badge} <b>{count}. {title}</b> — <code>{price} ₽</code>\n"
            f"📦 <b>Данные:</b>\n"
            f"<code>{safe_data}</code>"
        )

    text = (
        "📜 <b>История последних покупок:</b>\n\n"
        + "\n───────────────\n".join(all_purchases)
    )

    await callback.message.answer(text=text,parse_mode="HTML")
    await callback.answer()

#проверка подписки на канал
@user_router.callback_query(F.data == "sub_check")
async def check_sub_channel(callback: CallbackQuery):
    # Сюда попадают только подписанные пользователи
    await callback.message.answer("✅ Подписка подтверждена! Доступ открыт.")
