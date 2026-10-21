import math
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Categories, Items, SubCategories, Products, User
from database.queries import ProductsQueries
from aiogram.exceptions import TelegramBadRequest
from config.config import settings
from handlers.admin import ADMIN_IDS
from keyboards.inline import (
    CategoryCD,
    ItemsCD,
    ItemsPageCD,
    SubCategoryCD,
    keyboard_categories,
    item_card_keyboard,
    sub_categories_kb,
    items_pagination_keyboards,
    mass_loading_kb,
    confirm_mass_buy_kb,
)
#FSM состояние для ввода кол-ва покупаемого товара
class MassEnterState(StatesGroup):
    waiting_for_count = State()


catalog_router = Router()

@catalog_router.message(F.text == "Каталог товаров 🛒")
async def open_catalog(message: Message, session: AsyncSession):

    is_admin = message.from_user.id in ADMIN_IDS
    categories = await ProductsQueries.get_all_categories(session)

    if not categories:
        return await message.answer("Каталог пока пуст. Скоро здесь появятся товары!")

    photo = FSInputFile("images/catalog.jpg")
    
    await message.answer_photo(
        photo=photo,
        caption="Выберите интересующий раздел:",
        reply_markup=keyboard_categories(categories,is_admin)
        )
    
@catalog_router.callback_query(CategoryCD.filter())
async def show_category_pagination(callback: CallbackQuery,callback_data: CategoryCD, session: AsyncSession):
    is_admin = (
        callback.from_user.id in ADMIN_IDS
    )
    category_id = callback_data.category_id

    sub_cat = (await session.scalars(select(SubCategories).where(SubCategories.category_id == callback_data.category_id))).all()
    
    if not sub_cat and not is_admin:
        return await callback.answer("⚠️ В этом разделе пока нет товара.", show_alert=True)

    await callback.message.delete()
    await callback.message.answer("Выберите подкатегорию:", reply_markup=sub_categories_kb(category_id, sub_cat, is_admin))
    await callback.answer()

@catalog_router.callback_query(SubCategoryCD.filter())
async def sub_categories(callback: CallbackQuery, callback_data: SubCategoryCD, session: AsyncSession):
    is_admin = (
        callback.from_user.id in ADMIN_IDS
    )
    # ID конкретной выбранной подкатегории
    sub_category_id = callback_data.sub_category_id

    sub_category = await session.get(SubCategories, sub_category_id)

    if not sub_category:
        return await callback.answer("⚠️ Подкатегория не найдена", show_alert=True)

    mass_product = await session.scalar(select(Products).where(Products.subcategory_id == sub_category_id))

    if mass_product:
        stock_stmt = select(func.count(Items.id)).where(
            Items.product_id == mass_product.id,
            Items.is_sold.is_(False)
        )

        stock = await session.scalar(stock_stmt) or 0

        if stock == 0 and not is_admin:
            return await callback.answer(
                "⚠️ Товара временно нет в наличии", show_alert=True
            )
        
        text = (
            f"📦 <b>{mass_product.name}</b>\n\n"
            f"{mass_product.description}\n\n"
            f"💵 <b>Цена:</b> {mass_product.price} ₽ / шт.\n"
            f"📊 <b>В наличии:</b> {stock} шт.\n\n"
            "🔢 Выберите количество: "

        )

        return await callback.message.edit_text(
            text=text,
            reply_markup=mass_loading_kb(stock, mass_product.id, sub_category_id, is_admin),
            parse_mode="HTML"
        )



    page = 1
    ITEMS_PER_PAGE = 5
    
    
    is_product = (await session.scalars(select(Items.id).where(Items.category_id == sub_category_id).where(Items.is_sold.is_(False)))).all()

    if not is_product and not is_admin:
            return await callback.answer("⚠️ В этой подкатегории пока нет товаров в наличии",show_alert=True)
    
    offset, total_page, items = await ProductsQueries.get_items(
        session, page, ITEMS_PER_PAGE, sub_category_id
    )

    text = f"📦 <b>Товары {sub_category.name}</b>\n\n"
    await callback.message.edit_text(
        text=text,
        reply_markup=items_pagination_keyboards(
            page=page,
            total_page=total_page,
            category_id=sub_category_id,
            items=items,
            is_admin=is_admin
        ),
        parse_mode='HTML'
    )
    await callback.answer()

@catalog_router.callback_query(ItemsPageCD.filter())
async def pagination_button(callback: CallbackQuery, callback_data: ItemsPageCD, session: AsyncSession):

    is_admin = (
        callback.from_user.id in ADMIN_IDS
    )

    sub_category_id = callback_data.category_id
    page = callback_data.page
    ITEMS_PER_PAGE = 5

    sub_category = await session.get(SubCategories, sub_category_id)
    if not sub_category:
        return await callback.answer("⚠️ Подкатегория не найдена", show_alert=True)

    offset, total_page, items = await ProductsQueries.get_items(
        session, page, ITEMS_PER_PAGE, sub_category_id
    )

    text = f"📦 <b>Товары {sub_category.name}</b>\n\n"

    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=items_pagination_keyboards(
                page=page,
                total_page=total_page,
                category_id=sub_category_id,
                items=items,
                is_admin=is_admin
            ),
            parse_mode='HTML'
        )

    except TelegramBadRequest as e:
        if "message is not modified" not in e.message:
            raise e

    await callback.answer()

#---------------------------------выбор количества товара-------------------------------------
@catalog_router.callback_query(F.data == "cancel_mass_enter", MassEnterState.waiting_for_count)
async def cancel_enter(callback: CallbackQuery, state: FSMContext):
      await state.clear()
      await callback.message.edit_text("🚫 Покупка отменена")
      await callback.answer()
    
@catalog_router.callback_query(F.data.startswith("enter_mass"))
async def enter_mass_count(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split(":")[-1])

    await state.update_data(product_id=product_id, catalog_msg_id=callback.message.message_id)

    await state.set_state(MassEnterState.waiting_for_count)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mass_enter")]
        ]
    )

    await callback.message.answer(
      "🔢 <b>Введите нужное количество штук цифрой:</b>\n"
      "<i>(Например: 3, 7, 15)</i>",
      reply_markup=cancel_kb,
      parse_mode="HTML",
    )

    await callback.answer()

@catalog_router.message(MassEnterState.waiting_for_count)
async def enter_mass_confirm(message: Message, user: User, bot: Bot, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()

    if not text.isdigit() or len(text) > 6 or int(text) <= 0:
        return await message.answer(
            "❌ Стоимость товара должна быть целым положительным числом (например: <code>5</code>)",
            parse_mode="HTML",
        )
    
    count_enter = int(text)
    data_fsm = await state.get_data()
    product_id = data_fsm.get("product_id")
    catalog_msg_id = data_fsm.get("catalog_msg_id")

    product = await session.get(Products, product_id)
    if not product:
        await state.clear()
        return await message.answer(
            "❌ Ошибка: товар не найден или был удален."
        )

    count_product = await session.scalar(
        select(func.count(Items.id)).
        where(Items.product_id == product_id, Items.is_sold.is_(False))
        ) or 0

    if count_product == 0:
        await state.clear()
        return await message.answer(
            "❌ К сожалению, этот товар только что закончился!"
        )

    if count_enter > count_product:
        return await message.answer(
            f"❌ Нельзя купить больше, чем есть в наличии!\n"
            f"📊 Доступно штук: <b>{count_product}</b>\n\n"
            f"Попробуйте ввести меньшее число:",
            parse_mode="HTML",
        )

    await state.clear()

    price = count_enter * product.price

    if user.balance < price:
        return await message.answer(
            f"❌Недостаточно средств!\n"
            f"Нужно: {price:.2f} ₽\n"
            f"На балансе: {user.balance:.2f} ₽"
        )

    text_confirm = (
        f"⚠️ <b>Подтверждение покупки</b>\n\n"
        f"📦 Товар: <b>{product.name}</b>\n"
        f"🔢 Количество: <b>{count_enter} шт.</b>\n"
        f"💵 К списанию: <b>{price:.2f} ₽</b> (по {product.price:.2f} ₽/шт.)\n"
        f"🪙 Ваш баланс: <b>{user.balance:.2f} ₽</b>\n\n"
        f"С вашего баланса спишется <b>{price:.2f} ₽</b>. Подтверждаете?"
    )

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=catalog_msg_id,
        text=text_confirm,
        reply_markup=confirm_mass_buy_kb(product_id, count_enter),
        parse_mode="HTML",
    )
#обработка кнопок для массовой покупки (1, 5, 10) шт
@catalog_router.callback_query(F.data.startswith("buy_mass"))
async def mass_buy_number(callback: CallbackQuery, user: User, session: AsyncSession):

    _, product_id_str, count_str = callback.data.split(":")

    product_id = int(product_id_str)
    count = int(count_str)

    product = await session.get(Products, product_id)

    if not product:
        return await callback.answer(
            "❌ Ошибка: товар не найден или был удален."
        )


    count_product = await session.scalar(
        select(func.count(Items.id)).
        where(Items.product_id == product_id, Items.is_sold.is_(False))
        ) or 0
    
    if count_product == 0:
        return await callback.answer(
            "❌ К сожалению, этот товар только что закончился!"
        )

    if count_product < count:
        return await callback.answer(
        f"❌ Недостаточно товара! Доступно всего: {count_product} шт.", show_alert=True
        )

    price = count * product.price

    if user.balance < price:
        return await callback.answer(
            f"❌ <b>Недостаточно средств!</b>\n"
            f"Нужно: {price:.2f} ₽\n"
            f"На балансе: {user.balance:.2f} ₽",
            parse_mode="HTML",
        )
    
    await callback.answer()

    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение покупки</b>\n\n"
        f"📦 Товар: <b>{product.name}</b>\n"
        f"🔢 Количество: <b>{count} шт.</b>\n"
        f"💵 К списанию: <b>{price:.2f} ₽</b> (по {product.price:.2f} ₽/шт.)\n"
        f"🪙 Ваш баланс: <b>{user.balance:.2f} ₽</b>\n\n"
        f"С вашего баланса спишется <b>{price:.2f} ₽</b>. Подтверждаете?",
        parse_mode="HTML",
        reply_markup=confirm_mass_buy_kb(product_id, count)
  )

@catalog_router.callback_query(ItemsCD.filter())
async def back_to_product(callback: CallbackQuery, callback_data: ItemsCD, session: AsyncSession):
    is_admin = (
        callback.from_user.id in ADMIN_IDS
    )
    item_id = callback_data.item_id
    item = await session.scalar(select(Items).where(Items.id == item_id, Items.is_sold.is_(False)))

    if not item:
        return await callback.answer("Товар купили!",show_alert=True)
    text = (
         f"<b>{item.title}</b>\n\n"
         f"{item.description}\n\n"
         f"🪙Цена: {item.price}"
    )
    try:
        photo_url = item.photo
        await callback.message.edit_text(text,reply_markup=item_card_keyboard(item_id, photo_url, item.category_id, is_admin=is_admin),parse_mode='HTML')

    except TelegramBadRequest as e:
        if "message is not modified" not in e.message:
            raise e
        
    await callback.answer()


@catalog_router.callback_query(F.data == "back_to_categories")
async def back_to_categories_menu(callback: CallbackQuery, session: AsyncSession):
    is_admin = callback.from_user.id in ADMIN_IDS
    categories = await ProductsQueries.get_all_categories(session)
    if not categories:
        return await callback.answer("Каталог пока пуст. Скоро здесь появятся товары!")

    await callback.message.delete()
    photo = FSInputFile("images/catalog.jpg")

    await callback.message.answer_photo(
        photo=photo,
        caption="Выберите интересующий раздел:",
        reply_markup=keyboard_categories(categories, is_admin)
    )


