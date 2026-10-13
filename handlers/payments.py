from config.config import settings
from payments.crypto_pay import CryptoPay
from keyboards.inline import BuyCD, top_up_balance_crypto_kb, confirm_buy_item
from database.models import Items, Payments, User, Orders, Products
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError
from decimal import Decimal
from handlers.admin import ADMIN_IDS
import html

router_pay = Router()
crypto = CryptoPay(settings.CRYPTO_PAY_TOKEN)


"""Код выдачи товара сразу после оплаты, без пополнение баланса (Прошлый вариант)"""
# @router_pay.callback_query(BuyCD.filter())
# async def payment_product(callback: CallbackQuery,callback_data: BuyCD, session: AsyncSession):
#     item = await session.get(Items,callback_data.item_id)

#     if not item:
#         return await callback.answer("Товар не найден или удален", show_alert=True)
    
#     if item.is_sold:
#         return await callback.answer("Товар куплен другим пользователем",show_alert=True)

    
#     invoice = await crypto.create_invoice(
#         amount=item.price,
#         )
#     if not invoice:
#         return await callback.answer("Ошибка связи с платежкой, попробуйте позже.", show_alert=True)

#     await callback.message.answer(f"Счет #{invoice['invoice_id']} сформирован.\nПосле оплаты нажмите кнопку проверки:",reply_markup=check_pay_keyboard(invoice,callback_data.item_id))

# @router_pay.callback_query(PayCheckCD.filter())
# async def check_payment(callback: CallbackQuery, callback_data: PayCheckCD,session: AsyncSession):
#     invoice = await crypto.get_invoice(callback_data.invoice_id)

#     if not invoice:
#         return await callback.answer("Не удалось найти счет. Попробуйте еще раз.",show_alert=True)

#     status = invoice.get("status")

#     if status == "active":
#         return await callback.answer("Оплата пока не поступила. Подождите пару секунд и проверьте снова.", show_alert=True)

#     if status != "paid":
#         return await callback.answer(f"Счет не действителен (статус: {status}).", show_alert=True)

#     stmt = (
#         update(Items).
#         where(Items.id == callback_data.item_id, Items.is_sold.is_(False))
#         .values(is_sold = True)
#         .returning(Items.data)
#     )

#     result = await session.execute(stmt)

#     item_data = result.scalar_one_or_none()

#     await session.commit()

#     if item_data is None:
#         return await callback.answer("Этот товар уже был выдан!", show_alert=True)
#     await callback.message.edit_reply_markup(reply_markup=None)

#     await callback.message.answer(
#         f"Оплата подтверждена!\n\n"
#         f"Ваш товар:\n`{item_data}`",
#         parse_mode="Markdown",
#     )
#     await callback.answer()

# Пополнение баланса

class TopUpBalance(StatesGroup):
    waiting_for_amount = State()


@router_pay.callback_query(F.data == "cancel_balance", TopUpBalance.waiting_for_amount)
async def cancel_top_up_balance(callback: CallbackQuery, state: FSMContext):
   await state.clear()
   await callback.message.edit_text("🚫 Пополнение баланса отменено")
   await callback.answer()

@router_pay.message(F.text == "Пополнить баланс 📥")
async def top_up_balance_message(message: Message, state: FSMContext):
    cancel_kb = InlineKeyboardMarkup(
    inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_balance")]
        ]
    )

    await state.set_state(TopUpBalance.waiting_for_amount)
    await message.answer("Введите сумму пополнения в рублях (минимум 50 ₽):", reply_markup=cancel_kb)

@router_pay.callback_query(F.data == "top_up_balance")
async def top_up_balance_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    cancel_kb = InlineKeyboardMarkup(
    inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_balance")]
        ]
    )


    await state.set_state(TopUpBalance.waiting_for_amount)
    await callback.message.answer("Введите сумму пополнения в рублях (минимум 50 ₽):", reply_markup=cancel_kb)

@router_pay.message(TopUpBalance.waiting_for_amount)
async def process_top_up(message: Message, state: FSMContext):
    MIN_AMOUNT = 50
    MAX_AMOUNT = 10_000

    amount = message.text

    if not amount.isdigit() or len(amount) > 6:
        return await message.answer("❌ Пожалуйста, введите целое положительное число")

    if int(amount) < MIN_AMOUNT:
        return await message.answer("❌ Минимальная сумма поплнения - 50 ₽")
    
    if int(amount) > MAX_AMOUNT:
        return await message.answer("❌ Максимальная сумма пополнения за одну транзакцию- 10.000 ₽")
    
    await state.clear()

    invoice = await crypto.create_invoice(
        amount=amount
    )

    await message.answer(f"Счёт на сумму **{amount} ₽** сформирован. После оплаты нажмите «Проверить оплату».",reply_markup=top_up_balance_crypto_kb(amount,invoice))

#отмена счета
@router_pay.callback_query(F.data.startswith("cancel_crypto_payments"))
async def cancel_crypto_invoice_handler(callback: CallbackQuery):
    invoice_id = int(callback.data.split(":")[-1])

    await callback.message.edit_text(f"🚫 Счет с идентификатором <code>#{invoice_id}</code> был отменен", parse_mode="HTML")
    await callback.answer()


@router_pay.callback_query(F.data.startswith("check_pay_crypto"))
async def check_payment(callback: CallbackQuery,session: AsyncSession):
    invoice_id = int(callback.data.split(":")[-1])
    invoice = await crypto.get_invoice(invoice_id)

    if not invoice:
        return await callback.answer("Не удалось найти счет. Попробуйте еще раз.",show_alert=True)

    invoice_status = invoice.get("status")

    if invoice_status == "active":
        return await callback.answer("Оплата пока не поступила. Подождите пару секунд и проверьте снова.", show_alert=True)
    
    if invoice_status != "paid":
        return await callback.answer(f"Счет не действителен (статус: {invoice_status}).", show_alert=True)

    check_stmt = (select(Payments).where(Payments.invoice_id == invoice_id, Payments.status == "paid"))
    execute_check_stmt = (await session.execute(check_stmt)).scalar_one_or_none()

    if execute_check_stmt:
        return await callback.answer("Этот счет уже был успешно зачислен!", show_alert=True)

    amount = Decimal(str(invoice.get("amount",0)))


    new_payment = Payments(
        user_id=callback.from_user.id,
        invoice_id=invoice_id,
        amount=invoice.get("amount"),
        payment_system="CryptoBot",
        status=invoice_status,
    )

    top_up_balance_user = (
        update(User).
        where(User.tg_id == callback.from_user.id).
        values(balance=User.balance + amount).
        returning(User.balance)
    )
    result = await session.execute(top_up_balance_user)
    new_balance = result.scalar_one_or_none()


    session.add(new_payment)
    await session.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Оплата прошла успешно!\n\n"
        f"Пополнено: **{amount} ₽**\n"
        f"Ваш текущий баланс: **{new_balance} ₽**",
        parse_mode="Markdown",
    )
    await callback.answer()


#Оплата товара с подтверждением покупки
@router_pay.callback_query(F.data.startswith("buy_item"))
async def confirm_buy_item_handler(callback: CallbackQuery, session: AsyncSession):
    item_id = int(callback.data.split(":")[-1])

    item = await session.get(Items, item_id)
    user = await session.scalar(select(User).where(User.tg_id == callback.from_user.id))

    if not item or item.is_sold:
        return await callback.answer("❌ Товар уже продан!", show_alert=True)
    
    category_id = item.category_id
    
    if user.balance < item.price:
        return await callback.answer(
            f"❌ Недостаточно средств! Нужно: {item.price:.2f} ₽, на балансе: {user.balance:.2f} ₽",
            show_alert=True,
        )
    

    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение покупки</b>\n\n"
        f"📦 Товар: <b>{item.title}</b>\n"
        f"💵 К списанию: <b>{item.price:.2f} ₽</b>\n"
        f"🪙 Ваш баланс: <b>{user.balance:.2f} ₽</b>\n\n"
        f"С вашего баланса спишется <b>{item.price:.2f} ₽</b>. Подтверждаете?",
        parse_mode="HTML",
        reply_markup=confirm_buy_item(item_id, category_id)
    )

    await callback.answer()


#Полноценная оплата товара
@router_pay.callback_query(BuyCD.filter())
async def buy_product(
    callback: CallbackQuery, callback_data: BuyCD, session: AsyncSession, bot: Bot
):
    item_id = callback_data.item_id

    
    user = await session.scalar(
        select(User).where(User.tg_id == callback.from_user.id)
    )
    if not user:
        return await callback.answer(
            "Пользователь не найден.", show_alert=True
        )

    item = await session.scalar(
        select(Items).where(Items.id == item_id, Items.is_sold.is_(False))
    )
    if not item:
        return await callback.answer(
            "Товар не найден или уже продан!", show_alert=True
        )

    if user.balance < item.price:
        diff = item.price - user.balance
        return await callback.answer(
            f"Недостаточно средств! Не хватает {diff:.2f} ₽.",
            show_alert=True,
        )

    user.balance -= item.price
    item.is_sold = True

    # 5. Создаем заказ
    new_order = Orders(
        user_id=user.tg_id,
        name=item.title,
        item_id=item.id,
        price=item.price,
        purchase_price=item.purchase_price,
        item_data=item.data,
        
    )
    session.add(new_order)

    await session.commit()


    await callback.message.edit_reply_markup(reply_markup=None)

    safe_data = html.escape(str(item.data))

    await callback.message.edit_text(
        f"✅ <b>Покупка успешно совершена!</b>\n\n"
        f"Списано: <code>{item.price} ₽</code>\n"
        f"Остаток: <code>{user.balance} ₽</code>\n\n"
        f"📦 <b>Данные товара:</b>\n<pre>{safe_data}</pre>",
        parse_mode="HTML",
    )
    await callback.answer()


    #уведомляем админа
    profit = item.price - (item.purchase_price or 0)
    username_str = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else "отсутствует"
    )

    admin_text = (
        f"🛍 <b>Новая покупка! (Заказ #{new_order.id})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Покупатель:</b> {html.escape(callback.from_user.full_name)} (<code>{user.tg_id}</code>)\n"
        f"🔗 <b>Username:</b> {username_str}\n"
        f"📦 <b>Товар:</b> {html.escape(item.title)} (ID: <code>{item.id}</code>)\n"
        f"💵 <b>Цена продажи:</b> <code>{item.price:.2f} ₽</code>\n"
        f"📉 <b>Себестоимость:</b> <code>{item.purchase_price:.2f} ₽</code>\n"
        f"📈 <b>Прибыль:</b> <code>+{profit:.2f} ₽</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    refund_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Возврат средств", callback_data=f"refund_user:{new_order.id}")]
        ]
    )
    await bot.send_message(
        chat_id=ADMIN_IDS[0],
        text=admin_text,
        parse_mode="HTML",
        reply_markup=refund_kb
    )

#массовая оплата товара
@router_pay.callback_query(F.data.startswith("confirm_mass"))
async def buy_mass_product(callback: CallbackQuery, user: User, bot: Bot, session: AsyncSession):
    _, product_id_str, count_str = callback.data.split(":")

    product_id = int(product_id_str)
    count = int(count_str)

    product = await session.get(Products, product_id)
    
    if not product:
        return await callback.answer(
            "❌ Ошибка: товар не найден или был удален."
        )

    items = (await session.scalars(
        select(Items).where(
        Items.product_id == product_id, Items.is_sold.is_(False)
        ).limit(count))).all()

    if len(items) < count:
        return await callback.answer(
        f"❌ Недостаточно товара! Доступно всего: {len(items)} шт.",
        show_alert=True,
    )

    price = count * product.price
    
    if user.balance < price:
        return await callback.answer(
        f"❌ Недостаточно средств!\nНужно: {price:.2f} ₽\nБаланс: {user.balance:.2f} ₽",
        show_alert=True,
    )

    user.balance -= price

    purchase_price = Decimal("0.00")
    data_lines = []
    for item in items:
        item.is_sold = True
        purchase_price += item.purchase_price or Decimal("0.00")
        data_lines.append(item.data)

    all_data = "\n".join(data_lines)

    new_order = Orders(
        user_id=user.tg_id,
        name=f"{product.name} (x{count})",
        item_id=items[0].id,
        price=price,
        purchase_price=purchase_price,
        item_data=all_data,
    )

    session.add(new_order)
    await session.commit()

    await callback.message.edit_reply_markup(reply_markup=None)

    

    data_text = (
        f"✅ <b>Покупка успешно совершена!</b>\n\n"
        f"📦 Товар: <b>{html.escape(product.name)}</b>\n"
        f"🔢 Количество: <b>{count} шт.</b>\n"
        f"💵 Списано: <code>{price:.2f} ₽</code>\n"
        f"🪙 Остаток на балансе: <code>{user.balance:.2f} ₽</code>\n\n"
        # f"🔑 <b>Данные товаров:</b>\n<pre>{safe_data}</pre>",
    )

    if count <= 5:
        safe_data = html.escape(all_data)
        await callback.message.answer(
            f"{data_text}\n🔑 <b>Данные:</b>\n<pre>{safe_data}</pre>",
            parse_mode="HTML",
    )

    else:
        await callback.message.edit_text(
            f"{data_text}\n\n📁 <i>Файл с вашими аккаунтами отправлен ниже 👇</i>",
            parse_mode="HTML",
        )

        file_bytes = new_order.item_data.encode("utf-8")
        document = (
            BufferedInputFile(
                file=file_bytes, filename=f"order_{new_order.id}.txt"
            )
        )
        await callback.message.answer_document(
            document=document,
            caption=f"📄 Файл с товарами к заказу <b>#{new_order.id}</b>",
            parse_mode="HTML",
        )


    await callback.answer()

    profit = price - int(purchase_price)

    username_str = (
        f"@{callback.from_user.username}" 
        if callback.from_user.username
        else "отсутствует"
    )

    profit_str = ""
    if profit >=0 :
        profit_str = f"+{profit:.2f}"
    else:
        profit_str = f"{profit:.2f}"

    admin_text = (
        f"🛍 <b>Новая массовая покупка! (Заказ #{new_order.id})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Покупатель:</b> {html.escape(callback.from_user.full_name)} (<code>{user.tg_id}</code>)\n"
        f"🔗 <b>Username:</b> {username_str}\n"
        f"📦 <b>Лот:</b> {html.escape(product.name)} (ID: <code>{product.id}</code>)\n"
        f"🔢 <b>Количество:</b> <code>{count} шт.</code>\n"
        f"💵 <b>Сумма продажи:</b> <code>{price:.2f} ₽</code>\n"
        f"📉 <b>Себестоимость:</b> <code>{purchase_price:.2f} ₽</code>\n"
        f"📈 <b>Прибыль:</b> <code>{profit_str} ₽</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    refund_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Возврат средств", callback_data=f"refund_user:{new_order.id}")]
        ]
    )
    await bot.send_message(
        chat_id=ADMIN_IDS[0],
        text=admin_text,
        parse_mode="HTML",
        reply_markup=refund_kb
    )

#возврат средств
@router_pay.callback_query(F.data.startswith("refund_user"))
async def refund_handler(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    order_id = int(callback.data.split(":")[-1])

    order = await session.get(Orders, order_id)

    if not order:
        return await callback.answer("❌ Заказ не найден!", show_alert=True)

    if getattr(order, "refund", False):
        return await callback.answer(
            "⚠️ По этому заказу возврат уже был выполнен!", show_alert=True
        )

    user = await session.scalar(
        select(User).where(User.tg_id == order.user_id)
    )
    if not user:
        return await callback.answer(
            "❌ Пользователь не найден!", show_alert=True
        )

    user.balance += order.price
    order.refund = True

    await session.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("✅ Возврат успешно выполнен!", show_alert=True)

    try:
        await bot.send_message(
            chat_id=user.tg_id,
            text=(
                f"💳 <b>Оформлен возврат средств!</b>\n\n"
                f"За заказ <b>#{order.id}</b> ({order.name}) возвращено <b>{order.price:.2f} ₽</b> на ваш баланс бота.\n"
                f"🪙 Текущий баланс: <b>{user.balance:.2f} ₽</b>"
            ),
            parse_mode="HTML",
        )
    except TelegramAPIError:
        pass  # Если юзер заблокировал бота, хэндлер не упадет
