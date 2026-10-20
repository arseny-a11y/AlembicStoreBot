from aiogram.filters import BaseFilter, Command, StateFilter, or_f
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, TelegramObject, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError
from aiogram.types.error_event import ErrorEvent
from keyboards.reply import admin_menu 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,func, delete, update, or_
from database.models import Categories, Items, User, Orders, PromoCode, PromoUsage, SubCategories, Products
from keyboards.inline import category_admin, keyboard_categories, cancel_mailing_kb, generation_code_kb, sub_category_admin, orders_user_kb
from database.queries import CreatedCategories, check_promocode
from decimal import Decimal, InvalidOperation
from datetime import datetime, time
from config.config import settings
import operator
import asyncio
import string
import secrets
import traceback
import html
import io


admin_router = Router()
ADMIN_IDS = settings.ADMIN_IDS

class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        return event.from_user.id in ADMIN_IDS

admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())


# @admin_router.errors()
# async def error_handler(event: ErrorEvent, bot: Bot):
#     tb = "".join(
#         traceback.format_exception(
#             None, event.exception, event.exception.__traceback__
#         )
#     )
#     # Ограничиваем длину трейсбека под лимит сообщения Telegram
#     safe_tb = html.escape(tb[-3500:])

#     await bot.send_message(
#         chat_id=settings.ADMIN_IDS[0],
#         text=f"🚨 <b>Критическая ошибка:</b>\n<pre>{safe_tb}</pre>",
#         parse_mode="HTML",
#     )



#FSM состояние для загрузки товаров 
class AdminUploadItems(StatesGroup):
    waiting_for_category = State()
    waiting_for_sub_category = State()
    waiting_for_file = State()

class CreateCategory(StatesGroup):
    waiting_for_name = State()

class CreateSubCategory(StatesGroup):
    waiting_for_name = State()

#FSM состояние данных промокода
class PromoCodeState(StatesGroup):
    waiting_for_code = State()
    waiting_for_max_uses = State()
    waiting_for_amount = State()

#FSM состояние для редактирования товаров
class EditProductState(StatesGroup):
    waiting_for_data = State()
    waiting_for_price = State()

#FSM состояние для поплнения баланса через ID или @username
class AdminBalanceState(StatesGroup):
    waiting_for_identifier = State()
    waiting_for_amount = State()

#FSM состояние для массовой загрузки товаров
class MassLoadingState(StatesGroup):
    waiting_for_name = State()
    waiting_for_desc = State()
    waiting_for_price = State()
    waiting_for_file = State()

#FSM состояние для пополнения массового товара
class RestockMassState(StatesGroup):
    waiting_for_file = State()

#FSM состояние для редактирования цены массового товара
class MassEditPriceState(StatesGroup):
    waiting_for_price = State()

#FSM состояние для вывода покупок пользователя
class OrdersUserState(StatesGroup):
    waiting_for_order_id = State()
    waiting_for_identifier = State()

#FSM состояние для бана пользователя
class BannedUserState(StatesGroup):
    waiting_for_identifier = State()

#отмена всех FSM состояний
@admin_router.message(
    Command("cancel"), ~StateFilter(default_state)
)
async def cancel_text_handler(message: Message, state: FSMContext):
  current_state = await state.get_state()
  if current_state is None:
    return

  await state.clear()
  await message.answer(
      "🚫 Текущее действие отменено.",
  )

@admin_router.message(or_f(Command("admin"), F.text.in_(["🤖 Админка","админ"])))
async def admin_command(message: Message):
    await message.answer('Панель администратора открыта🫡',reply_markup=admin_menu())


#--------------------------------------отмена загрузки в категорию--------------------------------------
@admin_router.callback_query(
        F.data == "admin_cancel_upload",
        StateFilter(*AdminUploadItems, *RestockMassState)
        )
async def cancel_upload(callback: CallbackQuery, state: FSMContext):
   await state.clear()
   await callback.message.edit_text("🚫 Загрузка отменена")
   await callback.answer()

@admin_router.message(F.text == "📥 Загрузить товары (.txt)")
async def upload_items(message: Message, session: AsyncSession, state: FSMContext):
    
    categories = (await session.scalars(select(Categories))).all()
    is_admin = (
        message.from_user.id in ADMIN_IDS
    )
    if not categories:
        return await message.answer("Создайте хоть одну категорию!",reply_markup=keyboard_categories(categories, is_admin))

    
    await state.set_state(AdminUploadItems.waiting_for_category)
    await message.answer("Выберите категорию, в которую будут загружены товары:", reply_markup=category_admin(categories))


@admin_router.callback_query(AdminUploadItems.waiting_for_category, F.data.startswith("admin_cat"))
async def category_selected(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    category_id = int(callback.data.split(":")[-1])

    await state.set_state(AdminUploadItems.waiting_for_sub_category)

    sub_category = (await session.scalars(select(SubCategories).where(SubCategories.category_id == category_id))).all()

    if not sub_category:
        await state.clear()
        return await callback.message.edit_text("⚠️ В этой категории нет подкатегорий. Создайте подкатегорию перед загрузкой.")
        
    await callback.message.edit_text(
        "Категория выбрана.\n\n"
        "Выберите подкатегорию:",
        reply_markup=sub_category_admin(sub_category)
    )

    await callback.answer()


@admin_router.callback_query(AdminUploadItems.waiting_for_sub_category, F.data.startswith("admin_sub_cat"))
async def sub_category_selected(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    sub_category_id = int(callback.data.split(":")[-1])
    await state.update_data(sub_category_id=sub_category_id)

    await state.set_state(AdminUploadItems.waiting_for_file)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
            InlineKeyboardButton(text="📦 Массовая загрузка", callback_data=f"mass_loading:{sub_category_id}"),
            InlineKeyboardButton(text="📥 Пополнить товар", callback_data=f"top_up_mass_loading:{sub_category_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_upload")
            ]
        ]
    )

    await callback.message.edit_text(
        "📂 <b>Подкатегория выбрана.</b>\n\n"
        "Отправьте <b>.txt</b> файл со списком товаров документом.\n\n"
        "Формат каждой строки:\n"
        "<code>Название | Описание | Цена_продажи | Себестоимость | Данные_товара</code>\n\n"
        "<i>Пример:</i>\n"
        "<code>TikTok RU | Отлега 30д | 45.0 | 20.0 | login:pass:mail</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await callback.answer()


#--------------------------------------парсинг и загрузка товаров--------------------------------------
@admin_router.message(AdminUploadItems.waiting_for_file, F.document)
async def upload_items_file(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if not message.document.file_name.endswith(".txt"):
        return await message.answer("❌ Отправьте файл с расширением (.txt)")

    data_fsm = await state.get_data()
    document = message.document
    file_in_io = io.BytesIO()

    await bot.download(document,destination=file_in_io)

    file_in_io.seek(0)

    try:
        content: str = file_in_io.read().decode("utf-8")
    except UnicodeDecodeError:
       return await message.answer("❌ Ошибка: кодировка файла должна быть UTF-8.") 

    products = []

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    
    if not lines:
        return await message.answer("❌ Ошибка: файл пуст")

    for num, line in enumerate(lines,start=1):
        data_account = [d.strip() for d in line.split("|")]

        if len(data_account) not in (5, 6):
            return await message.answer(f"❌ Ошибка: в строке {num}: ожидалось 5 ИЛИ 6 полей через '|'")
        
        title, desc, price, purchase_price, data = data_account[:5]
        photo_url = data_account[5] if len(data_account) == 6 else None

        try:
            clean_price = Decimal(price.replace(",", "."))
            clean_purchase_price = Decimal(purchase_price.replace(",", "."))
        except InvalidOperation:
            return await message.answer(f"❌ Ошибка: Цена не является числом в строке {num}")

        products.append(
            Items(
                 category_id=data_fsm["sub_category_id"],
                 title=title,
                 description=desc,
                 price=clean_price,
                 purchase_price=clean_purchase_price,
                 data=data,
                 photo=photo_url,
                 is_sold=False
            )
        )
    session.add_all(products)
    await session.commit() 

    await state.clear()   
    await message.answer(f"✅ Успешно добавлено товаров: <b>{len(products)}</b> шт.", parse_mode="HTML")


#--------------------------------------массовая загрузка в 1 товар--------------------------------------
@admin_router.callback_query(F.data == "cancel_mass_loading", StateFilter(*MassLoadingState))
async def cancel_mass_loading_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Загрузка отменена")
    await callback.answer()


@admin_router.callback_query(F.data.startswith("mass_loading"))
async def mass_loading_name(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()

    sub_cat_id = int(callback.data.split(":")[-1])

    await state.set_state(MassLoadingState.waiting_for_name)

    await state.update_data(sub_cat_id=sub_cat_id)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mass_loading")]
        ]
    )

    await callback.message.answer("💬 Введите название товара: ", reply_markup=cancel_kb)       

@admin_router.message(MassLoadingState.waiting_for_name)
async def mass_loading_desc(message: Message, state: FSMContext):
    await state.update_data(name=message.text)

    await state.set_state(MassLoadingState.waiting_for_desc)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mass_loading")]
        ]
    )

    await message.answer("💬 Введите описание товара: ", reply_markup=cancel_kb)

@admin_router.message(MassLoadingState.waiting_for_desc)
async def mass_loading_price(message: Message, state: FSMContext):
    await state.update_data(desc=message.text)

    await state.set_state(MassLoadingState.waiting_for_price)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mass_loading")]
        ]
    )

    await message.answer("💬 Введите стоимость товара: ", reply_markup=cancel_kb)

@admin_router.message(MassLoadingState.waiting_for_price)
async def mass_loading_file(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    # 1. Проверяем валидность целого числа и длину
    if not text.isdigit() or len(text) > 6:
        return await message.answer(
            "❌ Стоимость товара должна быть целым положительным числом (например: <code>150</code>)",
            parse_mode="HTML",
        )
    
    clean_price = Decimal(text)
    if clean_price <= 0:
        return await message.answer("❌ Стоимость товара должна быть больше 0.")

    await state.update_data(price=str(clean_price))
    await state.set_state(MassLoadingState.waiting_for_file)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_mass_loading")]
        ]
    )

    await message.answer(
        "Отправьте <b>.txt</b> файл со списком товаров документом.\n\n"
        "Формат каждой строки:\n"
        "<code>Данные_товара | закупочная цена</code>\n\n"
        "<i>Пример:</i>\n"
        "<code>login:pass:mail | purchase price</code>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )


@admin_router.message(MassLoadingState.waiting_for_file, F.document)
async def mass_loading_products(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if not message.document.file_name.endswith(".txt"):
        return await message.answer("❌ Отправьте файл с расширением (.txt)")

    data_fsm = await state.get_data()
    document = message.document
    file_in_io = io.BytesIO()

    await bot.download(document, destination=file_in_io)

    file_in_io.seek(0)

    try:
        content: str = file_in_io.read().decode("utf-8")
    except UnicodeDecodeError:
        return await message.answer("❌ Ошибка: кодировка файла должна быть UTF-8.")


    products = []
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    if not lines:
        return await message.answer("❌ Ошибка: файл пуст")

    for num, line in enumerate(lines, start=1):
        data_account = [d.strip() for d in line.split("|")]

        if len(data_account) != 2:
            return await message.answer(f"❌ Ошибка: в строке {num}: ожидалось 2 поля через '|'")

        data, purchase_price = data_account

        try:
            clean_purchase_price = Decimal(purchase_price.replace(",", "."))
        except InvalidOperation:
            return await message.answer(f"❌ Ошибка: Закупочная цена не является числом в строке {num}")

        products.append((data, clean_purchase_price))

    new_product = Products(
        subcategory_id=data_fsm.get("sub_cat_id"),
        name=data_fsm.get("name"),
        description=data_fsm.get("desc"),
        price=data_fsm.get("price")
    )

    session.add(new_product)

    # Получаем ID созданного товара без закрытия транзакции
    await session.flush()

    items_to_add = [
        Items(
            category_id=data_fsm.get("sub_cat_id"),
            product_id=new_product.id,
            data=acc_data,
            purchase_price=p_price
        )
        for acc_data, p_price in products
    ]

    session.add_all(items_to_add)

    await session.commit()
    await state.clear()

    await message.answer(
      f"✅ <b>Лот успешно создан!</b>\n\n"
      f"📦 <b>Название:</b> {new_product.name}\n"
      f"💵 <b>Цена за шт:</b> {new_product.price} ₽\n"
      f"📊 <b>Загружено в лот:</b> {len(items_to_add)} шт.",
      parse_mode="HTML",
      reply_markup=admin_menu()
  )

#пополнение существующего массового товара
@admin_router.callback_query(F.data.startswith("top_up_mass_loading"))
async def top_up_mass_product(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    await callback.answer()

    sub_category_id = int(callback.data.split(":")[-1])

    # Находим существующий лот в этой категории
    product = await session.scalar(
      select(Products).where(Products.subcategory_id == sub_category_id)
    )

    if not product:
        return await callback.message.answer(
            "❌ В этой подкатегории ещё нет созданного товара.\n"
            "Сначала создайте его через «Массовая загрузка»."
        )

    count_products = await session.scalar(
        select(func.count(Items.id)).where(
            Items.product_id == product.id,
            Items.is_sold.is_(False)
        )
    ) or 0

    await state.update_data(product_id=product.id, sub_category_id=sub_category_id)

    await state.set_state(RestockMassState.waiting_for_file)

    cancel_kb = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text="❌ Отмена", callback_data="admin_cancel_upload"
          )
      ]]
    )
    await callback.message.answer(
      f"📥 <b>Пополнение лота:</b> {product.name}\n"
      f"📊 <b>Текущий остаток:</b> {count_products} шт.\n\n"
      f"Отправьте <b>.txt</b> файл с новыми строками документом.\n\n"
      f"<i>Формат строк:</i>\n"
      f"<code>данные_аккаунта | себестоимость</code>",
      reply_markup=cancel_kb,
      parse_mode="HTML",
  )

#ловим файл для пополнения товара
@admin_router.message(RestockMassState.waiting_for_file, F.document)
async def top_up_product_file(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):

    if not message.document.file_name.endswith(".txt"):
        return await message.answer("❌ Отправьте файл с расширением (.txt)")

    data_fsm = await state.get_data()
    product_id = data_fsm.get("product_id")
    sub_category_id = data_fsm.get("sub_category_id")

    document = message.document

    file_in_io = io.BytesIO()

    await bot.download(document, destination=file_in_io)

    file_in_io.seek(0)

    try:
        content: str = file_in_io.read().decode("utf-8")
    except UnicodeDecodeError:
        return await message.answer("❌ Ошибка: кодировка файла должна быть UTF-8.")


    products = []
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    if not lines:
        return await message.answer("❌ Ошибка: файл пуст")

    for num, line in enumerate(lines, start=1):
        data_account = [d.strip() for d in line.split("|")]

        if len(data_account) != 2:
            return await message.answer(f"❌ Ошибка: в строке {num}: ожидалось 2 поля через '|'")

        data, purchase_price = data_account

        try:
            clean_purchase_price = Decimal(purchase_price.replace(",", "."))
        except InvalidOperation:
            return await message.answer(f"❌ Ошибка: Закупочная цена не является числом в строке {num}")

        products.append((data, clean_purchase_price))

    items_to_add = [
        Items(
            category_id=data_fsm.get("sub_category_id"),
            product_id=product_id,
            data=acc_data,
            purchase_price=p_price
        )
        for acc_data, p_price in products
    ]
    
    session.add_all(items_to_add)
    
    await session.commit()
    await state.clear()
    
    product = await session.get(Products, product_id)

    await message.answer(
      f"✅ <b>Лот успешно пополнен!</b>\n\n"
      f"📦 <b>Товар:</b> {product.name}\n"
      f"➕ <b>Добавлено строк:</b> {len(items_to_add)} шт.",
      parse_mode="HTML",
    )

#удаление массового лота
@admin_router.callback_query(F.data.startswith("delete_mass_lot"))
async def delete_mass_lot_handler(callback: CallbackQuery, session: AsyncSession):
    sub_category_id = int(callback.data.split(":")[-1])

    product = await session.scalar(
        select(Products).where(
            Products.subcategory_id == sub_category_id
        )
    )

    if not product:
        return await callback.message.edit_text(
        " В этой подкатегории нет активного лота для удаления.")
    
    count_product = await session.scalar(
        select(func.count(Items.id)).where(
            Items.product_id == product.id,
            Items.is_sold.is_(False)
        )
    )

    confirm_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🔥 Да, удалить",
                  callback_data=f"confirm_delete_mass_lot:{product.id}",
              )
          ],
          [
              InlineKeyboardButton(
                  text="❌ Отмена", callback_data="cancel_del_mass"
              )
          ],
      ]
    )

    await callback.message.edit_text(
      f"⚠️ <b>Вы действительно хотите удалить этот лот?</b>\n\n"
      f"📦 <b>Товар:</b> {product.name}\n"
      f"📊 <b>Остаток на складе:</b> {count_product} шт.\n\n"
      f"<i>Все нераспроданные позиции ({count_product} шт.) будут безвозвратно удалены из базы!</i>",
      reply_markup=confirm_kb,
      parse_mode="HTML",
  )

#подтверждение удаления массового лота
@admin_router.callback_query(F.data.startswith("confirm_delete_mass_lot"))
async def conf_del_mass_lot(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()

    product_id = int(callback.data.split(":")[-1])

    product = await session.get(Products, product_id)

    if not product:
        return await callback.message.edit_text("❌ Товар уже был удален.")

    product_name = product.name

    await session.execute(
        delete(Items).where(
            Items.product_id == product_id,
            or_(Items.is_sold.is_(False), Items.is_sold.is_(None))
        )
    )


    sold_items = (await session.scalars(
        select(Items).where(
            Items.product_id == product.id,
            Items.is_sold.is_(True)
        )
    )).all()

    await session.execute(
      update(Items)
      .where(Items.product_id == product_id, Items.is_sold.is_(True))
      .values(product_id=None)
    )

    await session.delete(product)

    await session.commit()

    await callback.message.edit_text(
      f"🗑 <b>Лот «{product_name}» успешно удален из каталога!</b>\n\n"
      f"Витрина очищена, остатки удалены.", parse_mode="HTML")

#отмена удаления массового лота
@admin_router.callback_query(F.data == "cancel_del_mass")
async def cancel_del_mass_handler(callback: CallbackQuery, state: FSMContext):
   await state.clear()
   await callback.message.edit_text("🚫 Удаление отменено")
   await callback.answer()


#редактирование цены массового товара
@admin_router.callback_query(F.data.startswith("mass_edit_price"))
async def edit_price_mass_product_fsm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    product_id = int(callback.data.split(":")[-1])

    await state.set_state(MassEditPriceState.waiting_for_price)

    await state.update_data(product_id=product_id)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit_product")]
        ]
    )

    await callback.message.answer(
        "💰 Введите новую цену товара в рублях (например, <code>150</code>)",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )

@admin_router.message(MassEditPriceState.waiting_for_price)
async def edit_price_mass_product(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()

    try:
        clean_price = int(text)
        if clean_price <= 0 or clean_price > 999_999:
            raise ValueError
    except ValueError:
        return await message.answer(
            "❌ Стоимость товара должна быть целым положительным числом от 1 до 999 999 (например: <code>150</code>).",
            parse_mode="HTML",
        )

    new_price = Decimal(clean_price)
    
    data_fsm = await state.get_data()
    product_id = data_fsm.get("product_id")
    new_price = Decimal(text)
    
    product = await session.get(Products, product_id)

    if not product:
        await state.clear()
        return await message.answer("❌ Товар не найден в базе данных.")
    
    product.price = new_price

    await session.commit()
    await state.clear()

    return await message.answer(
        f"✅ Цена товара <b>{product.name}</b> успешно обновлена на <code>{new_price:.2f} ₽</code>!",
        parse_mode="HTML"
    )
#--------------------------------------Статистика продаж--------------------------------------
@admin_router.message(F.text == "📊 Статистика")
async def sales_stats(message: Message, session: AsyncSession):
    
    #дата 00-00 сегодняшнего числа
    from datetime import datetime, time, timezone

# Начало сегодняшнего дня строго в UTC:
    time_start = datetime.combine(
        datetime.now(timezone.utc).date(), time.min
        ).replace(tzinfo=None)

    #кол-во юзеров в боте
    all_user_in_bot = await session.scalar(select(func.count(User.id))) or 0 
    #кол-во юзеров в боте за сегодня
    users_for_day = await session.scalar(select(func.count(User.id)).where(User.registered_at >= time_start)) or 0
    #баланс на руках у юзеров
    users_balance = await session.scalar(select(func.sum(User.balance))) or 0

    #всего продано товаров за все время
    all_salles_count = await session.scalar(select(func.count(Orders.id)).where(Orders.refund.is_(False))) or 0
    #куплено товаров за сегодня 
    salles_for_day = await session.scalar(select(func.count(Orders.id)).where(Orders.purchased_at >= time_start, Orders.refund.is_(False))) or 0

    # кол-во товаров в наличии
    num_items_stock = await session.scalar(select(func.count(Items.id)).where(Items.is_sold.is_(False))) or 0

    #убыток за все время
    loss_all = await session.scalar(select(func.sum(Orders.purchase_price)).where(Orders.refund.is_(True))) or 0
    #убыток за сегодня
    loss_all_for_day = await session.scalar(select(func.sum(Orders.purchase_price)).where(Orders.purchased_at >= time_start, Orders.refund.is_(True))) or 0

    #выручка всего
    total_revenue = await session.scalar(select(func.sum(Orders.price)).where(Orders.refund.is_(False))) or 0
    #выручка за сегодня
    revenue_for_day = await session.scalar(select(func.sum(Orders.price)).where(Orders.purchased_at >= time_start, Orders.refund.is_(False))) or 0

    #чистыми за все время
    total_cost = await session.scalar(select(func.sum(Orders.purchase_price)).where(Orders.refund.is_(False))) or 0
    clean_money = total_revenue - total_cost - loss_all
    #чистыми за сегодня
    cost_for_day = await session.scalar(select(func.sum(Orders.purchase_price)).where(Orders.purchased_at >= time_start, Orders.refund.is_(False))) or 0
    clean_money_for_day = revenue_for_day - cost_for_day - loss_all_for_day


    #кол-во возвратов
    refund_count = await session.scalar(select(func.count(Orders.id)).where(Orders.refund.is_(True))) or 0
    #сумма возвратов
    refund_sum = await session.scalar(select(func.sum(Orders.price)).where(Orders.refund.is_(True))) or 0


    text = (
        "📊 **𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦 | Панель управления**\n\n"
        "👥 **Пользователи:**\n"
        f"├ Всего в боте: `{all_user_in_bot}` чел.\n"
        f"├ Новых за сегодня: `+{users_for_day}` чел.\n"
        f"└ Баланс на руках у юзеров: `{users_balance:.2f} ₽`\n\n"
        "📦 **Продажи и склад:**\n"
        f"├ Всего продано: `{all_salles_count}` шт.\n"
        f"├ Куплено сегодня: `{salles_for_day}` шт.\n"
        f"└ В наличии товаров: `{num_items_stock}` шт.\n\n"
        "💰 **Финансы:**\n"
        f"├ Выручка (всего): `{total_revenue:.2f} ₽`\n"
        f"├ Выручка за сегодня: `{revenue_for_day:.2f} ₽`\n"
        f"├ Чистыми за все время: `{clean_money:.2f} ₽`\n"
        f"└ Чистыми за сегодня: `{clean_money_for_day:.2f} ₽`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔄 **Возвратов:**\n `{refund_count}` шт на сумму: `{refund_sum:.2f}` ₽\n\n"
        f"⭕ **Убыток: **\n"
        f"├ За все время: `{loss_all:.2f} ₽`\n"
        f"└ За сегодня: `{loss_all_for_day:.2f} ₽`"
    )

    await message.answer(text=text,parse_mode="Markdown")


#управление товарами
@admin_router.message(F.text == "📦 Управление товарами")
async def product_managment(message: Message, session: AsyncSession):
    is_admin = (
        message.from_user.id in ADMIN_IDS
    )
    all_categories = (await session.scalars(select(Categories))).all()

    await message.answer(text="Выберите категорию для управления 📦", reply_markup=keyboard_categories(all_categories, is_admin=is_admin))

#--------------------------------------удаление категории--------------------------------------
@admin_router.callback_query(F.data.startswith("del_cat"))
async def delete_category(callback: CallbackQuery, session: AsyncSession):
    cat_id = int(callback.data.split(":")[-1])

    query = (select(Categories).where(Categories.id == cat_id))
    result = await session.execute(query)
    category = result.scalar_one_or_none()

    if not category:
        return await callback.answer("Категория уже удалена или не найдена.", show_alert=True)

    await session.delete(category)
    await session.commit()

    await callback.answer("Категория успешно удалена!")
    await callback.message.edit_text(f"✅ Категория #{cat_id} удалена.")

#--------------------------------------удаление подкатегории--------------------------------------
@admin_router.callback_query(F.data.startswith("delete_sub_cat"))
async def delete_sub_category(callback: CallbackQuery, session: AsyncSession):
    sub_category_id = int(callback.data.split(":")[-1])

    query = select(SubCategories).where(SubCategories.id == sub_category_id)
    result = await session.execute(query)
    sub_category = result.scalar_one_or_none()

    if not sub_category:
        return await callback.answer("Категория уже удалена или не найдена.", show_alert=True)

    await session.delete(sub_category)
    await session.commit()

    await callback.answer("Подкатегория успешно удалена!")
    await callback.message.edit_text(f"✅ Подкатегория #{sub_category_id} удалена.")
    

#----------ловит callback: admin_delete_item, для удаления конкретного товара--------
@admin_router.callback_query(F.data.startswith("admin_delete_item"))
async def delete_item(callback: CallbackQuery, session: AsyncSession):
    item_id = int(callback.data.split(":")[-1])

    del_item = (
        delete(Items).
        where(Items.id == item_id, Items.is_sold.is_(False))
    )
    result = await session.execute(del_item)
    await session.commit()

    if result.rowcount == 0:
        await callback.answer(
        "⚠️ Товар не найден или уже был куплен!", show_alert=True
    )

    else:
        await callback.answer("✅ Товар успешно удалён!", show_alert=True)
        await callback.message.edit_text("🗑 Товар был удалён из категории.")



#--------------------------------------создание и отмена создания категории--------------------------------------

@admin_router.callback_query(F.data == "cancel_create_cat", CreateCategory.waiting_for_name)
async def cancel_create_category(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Создание категории отменено")
    await callback.answer()

@admin_router.callback_query(F.data == "create_category")
async def created_category_button(callback: CallbackQuery,state: FSMContext):

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create_cat")]
        ]
    )

    await state.set_state(CreateCategory.waiting_for_name)
    await callback.message.edit_text("💬 Введите название категории: ", reply_markup=cancel_kb)
    await callback.answer()


@admin_router.message(CreateCategory.waiting_for_name)
async def created_category_fsm(message: Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip() if message.text else ""

    if not text:
        return await message.answer("❌ Название категории должно быть строкой")
    
    category_name = text
    
    await CreatedCategories.new_categories(session, category_name)

    await message.answer(f"✅ Категория «{category_name}» создана!")
    await state.clear()


#--------------------------------------создание и отмена создания подкатегорий--------------------------------------

@admin_router.callback_query(F.data == "cancel_create_subcat", CreateSubCategory.waiting_for_name)
async def cancel_create_subcategory(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Создание подкатегории отменено")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("create_sub_cat"))
async def create_sub_category(callback: CallbackQuery, state: FSMContext, session: AsyncSession):

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create_subcat")]
        ]
    )

    category_id = int(callback.data.split(":")[-1])
    await state.update_data(category_id=category_id)

    await state.set_state(CreateSubCategory.waiting_for_name)

    await callback.message.edit_text("💬 Введите название подкатегории: ", reply_markup=cancel_kb)
    await callback.answer()

@admin_router.message(CreateSubCategory.waiting_for_name)
async def created_sub_category_fsm(message: Message, state: FSMContext, session: AsyncSession):

    
    text = message.text.strip() if message.text else ""

    if not text:
        return await message.answer("❌ Название подкатегории должно быть строкой")

    data = await state.get_data()
    category_id = data.get("category_id")

    if not category_id:
        await state.clear()
        return await message.answer(
            "⚠️ Ошибка сессии: ID категории утерян. Попробуйте снова."
        )
    
    sub_category_name = text
  
    await CreatedCategories.new_sub_categories(session, sub_category_name,category_id)
    
    await state.clear()

    await message.answer(
        f"✅ Подкатегория <b>{text}</b> успешно создана!",
        parse_mode="HTML"
    )

#--------------------------------------редактирование данных товара--------------------------------------
@admin_router.callback_query(F.data.startswith("admin_edit_data"))
async def edit_data_product(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    await state.update_data(item_id=item_id)

    await state.set_state(EditProductState.waiting_for_data)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit_data")]
        ]
    )

    await callback.message.answer(f"💬 Введите новые данные товара: ",reply_markup=cancel_kb)
    await callback.answer()

@admin_router.message(EditProductState.waiting_for_data)
async def edit_data_product_fsm(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()

    if not text:
        return await message.answer(f"❌ Данные товара должны быть строкой")

    new_data = text
    data_fsm = await state.get_data()
    item_id = data_fsm.get("item_id")

    if not item_id:
        await state.clear()
        return await message.answer(
            "⚠️ Ошибка: ID товара утерян. Попробуйте снова."
        )
    
    item = await session.get(Items, item_id)
    if not item:
        await state.clear()
        return await message.answer("❌ Товар не найден в базе данных.")

    item.data = new_data

    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ Данные товара <b>#{item.id}</b> успешно обновлены на: <code>{new_data}</code>",
        parse_mode="HTML",
    )

#--------------------------------------редактирование цены товара--------------------------------------
@admin_router.callback_query(F.data.startswith("admin_edit_price"))
async def edit_price_product(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    await state.update_data(item_id=item_id)

    await state.set_state(EditProductState.waiting_for_price)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_edit_price")]
        ]
    )


    await callback.message.answer(f"💬 Введите новую стоимость товара: ",reply_markup=cancel_kb)
    await callback.answer()

@admin_router.message(EditProductState.waiting_for_price)
async def edit_price_product_fsm(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()

    # 1. Проверяем валидность целого числа и длину
    if not text.isdigit() or len(text) > 6:
        return await message.answer(
            "❌ Стоимость товара должна быть целым положительным числом (например: <code>150</code>)",
            parse_mode="HTML",
        )

    clean_price = Decimal(text)
    if clean_price <= 0:
        return await message.answer("❌ Стоимость товара должна быть больше 0.")

    data_fsm = await state.get_data()
    item_id = data_fsm.get("item_id")

    if not item_id:
        await state.clear()
        return await message.answer(
            "⚠️ Ошибка: ID товара утерян. Попробуйте снова."
        )

    item = await session.get(Items, item_id)
    if not item:
        await state.clear()
        return await message.answer("❌ Товар не найден в базе данных.")

    item.price = clean_price

    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ Стоимость товара <b>#{item.id}</b> успешно обновлена на: <b>{clean_price:.2f} ₽</b>!",
        parse_mode="HTML",
    )

# --------------------------------------Один хэндлер на обе отмены редактирования товаров--------------------------------------
@admin_router.callback_query(
    F.data.in_(["cancel_edit_data", "cancel_edit_price","cancel_edit_product"]),
    StateFilter(
        *EditProductState,
        *MassEditPriceState
    ),
)
async def cancel_edit_product_process(
    callback: CallbackQuery, state: FSMContext
):
    await state.clear()
    await callback.message.edit_text("🚫 Редактирование товара отменено.")
    await callback.answer()

#рассылка пользователям
class UserMailingState(StatesGroup):
    waiting_for_message = State()


#--------------------------------------отмена рассылки пользователям--------------------------------------
@admin_router.callback_query(F.data == "cancel_mailing", UserMailingState.waiting_for_message)
async def cancel_mailing(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Рассылка отменена")
    await callback.answer()

@admin_router.message(F.text == "👤 Рассылка")
async def user_mailing(message: Message, state: FSMContext):
    await state.set_state(UserMailingState.waiting_for_message)
    await message.answer(f"📢 Введите текст для рассылки всем пользователям бота: ",reply_markup=cancel_mailing_kb())

@admin_router.message(UserMailingState.waiting_for_message)
async def user_mailing_state(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear()

    ids_all_users = (await session.scalars(select(User.tg_id))).all()

    if not ids_all_users:
        return await message.answer("⚠️ В базе нет ни одного пользователя.")

    status_msg = await message.answer(f"⏳ Начинаю рассылку... Всего получателей: <code>{len(ids_all_users)}</code>",parse_mode="HTML")

    send_success = 0
    user_blocked = 0
    
    for chat_id in ids_all_users:
        if chat_id in ADMIN_IDS:
            continue
        try:
            await message.copy_to(chat_id=chat_id)
            send_success += 1

            await asyncio.sleep(0.05)

        except TelegramForbiddenError:
            user_blocked += 1
            continue

        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)

            await message.copy_to(chat_id=chat_id)
            send_success += 1

        except Exception:
            user_blocked += 1
            continue

    await status_msg.edit_text(
    "📊 <b>Рассылка завершена!</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    f"✅ Успешно доставлено: <code>{send_success}</code>\n"
    f"🚫 Не доставлено (блок бота): <code>{user_blocked}</code>\n"
    f"👥 Всего в базе: <code>{len(ids_all_users)}</code>\n"
    "━━━━━━━━━━━━━━━━━━━━━",
    parse_mode="HTML",
    )


#--------------------------------------создание промокодов--------------------------------------

#async функция по генерации промокодов и проверка существования в базе
async def generation_promo_code(session: AsyncSession, length: int = 8):
    exclude = "0O1I"

    all_symbol = string.ascii_uppercase + string.digits
    clear_symbol = ''.join(s for s in all_symbol if s not in exclude)

    while True:
        promo_code = ''.join(secrets.choice(clear_symbol) for i in range(length))
        existing = await check_promocode(session, promo_code)

        if existing is None:
            return promo_code


#--------------------------------------отмена создания промокода--------------------------------------
@admin_router.callback_query(
        F.data == "admin_cancel_promocode",
        StateFilter(*PromoCodeState)
        )
async def create_cancel_promocode(callback: CallbackQuery, state: FSMContext):
   await state.clear()
   await callback.message.edit_text("🚫 Создание промокода отменено")
   await callback.answer()

#--------------------------------------handler обработки нажатия кнопки и открытие FSM состояния--------------------------------------
@admin_router.message(F.text == "🎫 Создать промокод")
async def create_promocode(message: Message, state: FSMContext):
    await state.set_state(PromoCodeState.waiting_for_code)

    await message.answer("🎫 Введите или сгенерируйте промокод: ", reply_markup=generation_code_kb())

#--------------------------------------handler обработки нажатия "сгенерировать"--------------------------------------
@admin_router.callback_query(PromoCodeState.waiting_for_code, F.data == "gen_code")
async def generation_code(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    
    promo_code = await generation_promo_code(session=session)
    await state.update_data(code=promo_code)

    await state.set_state(PromoCodeState.waiting_for_max_uses)
    await callback.message.answer(f"✨ Ваш сгенерированный промокод: <code>{promo_code}</code>\n\nТеперь введите кол-во использований: ",parse_mode='HTML')

#--------------------------------------самостоятельный ввод промокода--------------------------------------
@admin_router.message(PromoCodeState.waiting_for_code)
async def waiting_for_promocode(message: Message, state: FSMContext, session: AsyncSession):

    if not message.text:
        return await message.answer("⚠️ Пожалуйста, отправьте промокод текстом (8 символов):")

    promo_code = message.text.strip().upper()

    if len(promo_code) != 8:
        return await message.answer("⚠️ Промокод должен содержать 8 символов. Попробуйте еще раз:")

    existing = await check_promocode(session, promo_code)

    if existing:
        await message.answer(
            f"❌ Промокод <code>{promo_code}</code> уже существует или использовался ранее.\n"
            "Введите другой промокод:",
            parse_mode="HTML"
        )
        return

    await state.update_data(code=promo_code)
    await state.set_state(PromoCodeState.waiting_for_max_uses)

    await message.answer(
        f"✅ Промокод <code>{promo_code}</code> принят!\n\n"
        "Теперь укажите <b>максимальное количество использований</b> (целое число):",
        parse_mode="HTML"
    )

#--------------------------------------обработа FSM состояния кол-ва использований--------------------------------------

@admin_router.message(PromoCodeState.waiting_for_max_uses)
async def max_uses(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""

    # Проверяем, что это строго положительное целое число
    if not text.isdigit() or int(text) <= 0:
        return await message.answer(
            "⚠️ Пожалуйста, введите положительное целое число (больше 0):"
        )

    uses_count = int(text)

    # Защита от неадекватно больших значений
    if uses_count > 100_000:
        return await message.answer(
            "⚠️ Слишком большое число. Введите значение до 100 000:"
        )

    cancel_kb = InlineKeyboardMarkup(
    inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_promocode")]
        ]
    )


    await state.update_data(max_uses=uses_count)
    await state.set_state(PromoCodeState.waiting_for_amount)

    await message.answer(
        f"✅ Лимит использований: <b>{uses_count}</b>\n\n"
        f"Теперь укажите <b>сумму награды</b> (целое число):",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )


# --------------------------------------обработа FSM состояния суммы вознаграждения--------------------------------------
@admin_router.message(PromoCodeState.waiting_for_amount)
async def amount_promocode(message: Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip() if message.text else ""

    # Проверяем, что это строго положительное целое число
    if not text.isdigit() or len(text) > 6 or int(text) <= 0:
        return await message.answer(
            "⚠️ Пожалуйста, введите положительное целое число (больше 0, не огромное):"
        )

    amount = int(text)
    

    data = await state.get_data()

    code = data.get("code")
    max_uses = data.get("max_uses")

    # Страховка на случай сброса состояния
    if not code or not max_uses:
        await state.clear()
        return await message.answer("⚠️ Данные устарели. Начните создание промокода заново.")

    create_promo = PromoCode(
        code=data.get("code"),
        max_uses=data.get("max_uses"),
        reward_amount=amount
    )

    session.add(create_promo)
    await session.commit()
    await state.clear()

    await message.answer(
        f"🎉 <b>Промокод успешно создан!</b>\n\n"
        f"Код: <code>{code}</code>\n"
        f"Активаций: <b>{max_uses}</b>\n"
        f"Награда: <b>{amount}</b>",
        parse_mode="HTML"
    )


#--------------------------------------поплнение баланса пользователя по ID или @username--------------------------------------
@admin_router.message(F.text == "💵 Управление балансом")
async def top_up_balance_user(message: Message, state: FSMContext):
    await state.set_state(AdminBalanceState.waiting_for_identifier)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="managment_balance")]
        ]
    )

    await message.answer("🔍 Введите (ID / @username) пользователя (обязательно с @): ",reply_markup=cancel_kb)

@admin_router.message(AdminBalanceState.waiting_for_identifier)
async def identifier_user_fsm(message: Message, state: FSMContext):

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="managment_balance")]
        ]
    )

    text = (message.text or "").strip()

    if not text:
        return await message.answer("❌ Пожалуйста, введите ID или @username пользователя")
    
    await state.update_data(identifier=text)
    await state.set_state(AdminBalanceState.waiting_for_amount)

    await message.answer("Введите (+ | -) и целое число, на которую вы измените баланс: ", reply_markup=cancel_kb)


@admin_router.message(AdminBalanceState.waiting_for_amount)
async def amount_user_fsm(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):

    text = (message.text or "").strip()

    if not text.startswith(("-", "+")):
        return await message.answer("❌ Число должно начинаться с (+ | -)")

    amount = text[1:]
    op = text[0]

    if not amount.isdigit():
        return await message.answer(
            "❌ Стоимость пополнения должна быть целым положительным числом (например: <code>150</code>)",
            parse_mode="HTML",
        )

    try:
        dec_amount = Decimal(amount)
    except Exception:
        return await message.answer("❌ Некорректное число.")

    if dec_amount <= 0 or dec_amount > 999_999:
        return await message.answer("❌ Сумма должна быть в диапазоне от 1 до 999 999.")
    
    data = await state.get_data()
    identifier = data.get("identifier")

    if not identifier:
        await state.clear()
        return await message.answer("❌ Ошибка сессии: идентификатор пользователя потерян. Начните заново.")
    
    if identifier.startswith("@"):
        username = identifier[1:].lower()

        user = await session.scalar(select(User).where(func.lower(User.username) == username))

    else:
        tg_id = identifier

        try:
            tg_id_int = int(tg_id)
        except ValueError:
            await state.clear()
            return await message.answer("❌ ID пользователя должен быть числом.")
        user = await session.scalar(select(User).where(User.tg_id == tg_id_int))


    if not user:
        await state.clear()
        return await message.answer(f"❌ Не удалось найти пользователя. Попробуйте снова...")
    
    tg_id_send = user.tg_id

    operation = {
        "+" : operator.add,
        "-": operator.sub
    }

    action = operation.get(op)
    if not action:
        await state.clear()
        return await message.answer("❌ Недопустимая операция.")

    new_balance = action(user.balance, dec_amount)

    if new_balance < 0:
        await state.clear()
        return await message.answer("❌ Операция отклонена: баланс не может стать отрицательным.")


    user.balance = new_balance

    await session.commit()
    await state.clear()

    await message.answer(f"✅ Баланс пользователя изменен на <b>{op}{amount}</b> ₽", parse_mode="HTML")

    try:
        if op == "+":
            text = (
                f"💳 <b>Пополнение баланса!</b>\n\n"
                f"Вам начислено: <b>+{dec_amount:.2f} ₽</b>\n"
                f"Текущий баланс: <b>{user.balance:.2f} ₽</b>"
            )
        else:
            text = (
                f"⚠️ <b>Корректировка баланса</b>\n\n"
                f"С вашего баланса списано: <b>-{dec_amount:.2f} ₽</b>\n"
                f"Текущий баланс: <b>{user.balance:.2f} ₽</b>"
            )

        await bot.send_message(
            chat_id=tg_id_send,
            text=text,
            parse_mode="HTML"
        )
    except TelegramAPIError:
        pass


#--------------------------------------отмена управления балансом--------------------------------------
@admin_router.callback_query(F.data == "managment_balance", StateFilter(*AdminBalanceState))
async def cancel_managment_balance(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🚫 Управление балансом отменено")
    await callback.answer()

#--------------------------------------поиск оредоров пользователей--------------------------------------
@admin_router.message(F.text == "🔍 Поиск заказов")
async def show_orders_user(message: Message):
    await message.answer(
      "🔍 <b>Выберите тип поиска:</b>\n\n"
      "• <b>По заказу:</b> мгновенный переход к деталям покупки и возврату\n"
      "• <b>По пользователю:</b> профиль, баланс и последние 10 заказов",
      reply_markup=orders_user_kb(),
      parse_mode="HTML",
  )

#поиск заказа по ID
@admin_router.callback_query(F.data == "search_by_order_id")
async def order_search_by_id(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await state.set_state(OrdersUserState.waiting_for_order_id)

    cancel_kb = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text="❌ Отмена", callback_data="cancel_search_order"
          )
      ]]
    )

    await callback.message.edit_text(
      "✍️ Введите <b>ID заказа</b> (число):",
      reply_markup=cancel_kb,
      parse_mode="HTML",
    )

@admin_router.message(OrdersUserState.waiting_for_order_id)
async def order_search_by_id_fsm(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()

    if not text.isdigit() or len(text) > 10 or int(text) <= 0:
        return await message.answer(
            "❌ ID должно быть целым положительным числом (например: <code>5</code>)",
            parse_mode="HTML",
        )
    order_id = int(text)

    order = await session.get(Orders, order_id)

    if not order:
        return await message.answer(
            f"❌ Заказ #{order_id} не найден в базе данных. Попробуйте еще раз..."
        )
    await state.clear()

    user = await session.scalar(select(User).where(User.tg_id == order.user_id))
    if not user:
        return await message.answer("❌ Пользователь не найден")
    
    username = user.username if user.username else "отсутствует"
    raw_item_data = order.item_data if order.item_data else "данные отсутствуют"

    refunf_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Возврат средств", callback_data=f"refund_user:{order.id}")]
        ]
    )
    status_badge = " [ ↩️ ВОЗВРАТ ]" if order.refund else ""

    order_info = (
        f"📦 <b>Заказ #{order.id}</b>  {status_badge}\n\n"
        f"👤 <b>ID клиента:</b> <code>{order.user_id}</code>\n"
        f"🏷 <b>Товар:</b> {order.name}\n"
        f"💰 <b>Сумма:</b> <code>{order.price} ₽</code>\n\n"
    )

    user_info = (
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Данные о покупателе #{user.tg_id}:\n"
        f"👤 <b>Username:</b> @{username}\n"
        f"👤 <b>Полное имя:</b> {html.escape(user.full_name or '')}\n"
        f"📆 <b>Дата регистрации:</b> <code>{user.registered_at}</code>\n"
        f"💰 <b>Баланс:</b> <code>{user.balance} ₽</code>"
    )

    if len(raw_item_data) > 500:
        text = (
          f"{order_info}"
          f"🔑 <b>Выданный товар:</b>\n"
          f"📁 <i>Данные слишком объемные и прикреплены файлом ниже 👇</i>\n\n"
          f"{user_info}"
        )

        await message.answer(text=text, parse_mode="HTML", reply_markup=refunf_kb)

        file_data = raw_item_data.encode("utf-8")
        document = BufferedInputFile(
            file_data, filename=f"order_{order.id}_data.txt"
        )

        await message.answer_document(
            document=document,
            caption=f"📄 Товар из заказа #{order.id}"
        )
    else:
        escaped_item_data = html.escape(raw_item_data)
        text = (
           f"{order_info}"
           f"🔑 <b>Выданный товар:</b>\n"
           f"<code>{escaped_item_data}</code>\n\n"
           f"{user_info}"
        )
        await message.answer(text=text, parse_mode="HTML", reply_markup=refunf_kb)

#поиск пользователя вместе с его заказами
@admin_router.callback_query(F.data == "search_by_user_orders")
async def search_orders_user(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await state.set_state(OrdersUserState.waiting_for_identifier)

    cancel_kb = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text="❌ Отмена", callback_data="cancel_search_order"
          )
      ]]
    )

    await callback.message.edit_text(
      "✍️ Введите (ID / @username) пользователя (обязательно с @): ",
      reply_markup=cancel_kb,
    )
@admin_router.message(OrdersUserState.waiting_for_identifier)
async def search_orders_user_fsm(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()
    
    if not text:
        return await message.answer("❌ Пожалуйста, введите ID или @username пользователя")

    identifier = text
    
    if identifier.startswith("@"):
        username = identifier[1:].lower()

        user = await session.scalar(select(User).where(func.lower(User.username) == username))

    else:
        tg_id = identifier
        
        try:
            tg_id_int = int(tg_id)
        except ValueError:
            return await message.answer("❌ ID пользователя должен быть числом.")
        
        user = await session.scalar(select(User).where(User.tg_id == tg_id_int))

    if not user:
        return await message.answer(f"❌ Не удалось найти пользователя. Попробуйте снова...")


    orders = (
        await session.scalars(
            select(Orders).
            where(Orders.user_id == user.tg_id).
            order_by(Orders.id.desc()).
            limit(10)
        )
    ).all()

    if not orders:
        await state.clear()
        return await message.answer(f"❌ У пользователя #{user.tg_id} нет приобретенных товаров")

    await state.clear()

    all_purchases = []

    for count, order in enumerate(orders, start=1):
        title = html.escape(order.name or "Товар")
        price = int(order.price)
        id = order.id

        raw_data = order.item_data or ""
        trimmed_data = raw_data[:200]
        safe_data = html.escape(trimmed_data)

        if len(raw_data) > 200:
            safe_data += "..."

        status_badge = " [ ↩️ ВОЗВРАТ ]" if order.refund else ""
        all_purchases.append(
            f"ID #{id}{status_badge} <b>{count}. {title}</b> — <code>{price} ₽</code>\n"
            f"📦 <b>Данные:</b>\n"
            f"<code>{safe_data}</code>"
        )

    username = user.username if user.username else "отсутствует"

    user_info = (
        f"\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Данные о покупателе #{user.tg_id}:\n"
        f"👤 <b>Username:</b> @{username}\n"
        f"👤 <b>Полное имя:</b> {html.escape(user.full_name or '')}\n"
        f"📆 <b>Дата регистрации:</b> <code>{user.registered_at}</code>\n"
        f"💰 <b>Баланс:</b> <code>{user.balance} ₽</code>"
        )
    
    text = (
        "📜 <b>История последних покупок:</b>\n\n"
        + "\n───────────────\n".join(all_purchases)
    )

    await message.answer(
        text=text + user_info,
        parse_mode="HTML"
    )
#отмена поиска заказов
@admin_router.callback_query(F.data == "cancel_search_order", StateFilter("*"))
async def cancel_upload(callback: CallbackQuery, state: FSMContext):
   await state.clear()
   await callback.message.edit_text("🚫 Поиск отменен")
   await callback.answer()

#--------------------------------------блокировка пользователя в боте--------------------------------------
@admin_router.message(F.text == "⭕ Бан пользователя")
async def banned_user(message: Message, state: FSMContext):
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_banned_user")]
        ]
    )

    await state.set_state(BannedUserState.waiting_for_identifier)
    await message.answer("🔎 Введите (ID / @username) пользователя ( обязательно с @ ) и действие (ban / unban): ",reply_markup=cancel_kb)

@admin_router.message(BannedUserState.waiting_for_identifier)
async def banned_user_fsm(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()

    if not text:
        return await message.answer("❌ Пожалуйста, введите ID или @username пользователя")

    try:
        identifier, action = text.split()
    except ValueError:
        return await message.answer("❌ Пожалуйста, введите ID или @username пользователя + (ban | unban)")
    
    if identifier.startswith("@"):
        username = identifier[1:].lower()

        user = await session.scalar(select(User).where(func.lower(User.username) == username))

    else:
        tg_id = identifier
        
        try:
            tg_id_int = int(tg_id)
        except ValueError:
            return await message.answer("❌ ID пользователя должен быть числом.")
        
        user = await session.scalar(select(User).where(User.tg_id == tg_id_int))

    if not user:
        return await message.answer(f"❌ Не удалось найти пользователя. Попробуйте снова...")

    # user.is_banned = True
    username = user.username if user.username else ""
    # await message.answer(f"Пользователь {username} <b>{user.full_name}</b> заблокирован ⭕")
    
    event = {
        "ban" : True,
        "unban" : False
    }

    
    if action not in event:
        return await message.answer("❌ Не удалось идентифицировать команду...")
    
    is_banned = event[action.lower()]

    if user.is_banned == is_banned:
        await state.clear()
        status_text = "уже забанен" if user.is_banned else "еще не забанен"
        return await message.answer(f"⚠️ Пользователь @{username} {status_text}. Действие не требуется.")

    user.is_banned = is_banned
    await session.commit()
    await state.clear()

    if is_banned:
        await message.answer(
        f"✅ Пользователь @{username} ({user.full_name}) заблокирован."
        )
    else:
        await message.answer(
            f"✅ Пользователь @{username} ({user.full_name}) разблокирован."
        )

@admin_router.callback_query(F.data == "cancel_banned_user", BannedUserState.waiting_for_identifier)
async def cancel_upload(callback: CallbackQuery, state: FSMContext):
   await state.clear()
   await callback.message.edit_text("🚫 Управление статусом пользователя отменено")
   await callback.answer()
