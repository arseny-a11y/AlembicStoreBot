from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from config.config import settings
def keyboard_support() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text='👤 Поддержка',url='https://t.me/gemaglobin')

    return kb.as_markup()

def keyboard_profile() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text='📂 История покупок',callback_data='history_purchases')
    kb.button(text='📥 Пополнить баланс',callback_data='top_up_balance')
    kb.button(text="🎫 Ввести промокод", callback_data="enter_promocode")

    kb.adjust(1)
    return kb.as_markup()


#функционал каталога
class CategoryCD(CallbackData,prefix='cat'):
    category_id: int

class SubCategoryCD(CallbackData, prefix='sub_cat'):
    sub_category_id: int

class ItemsCD(CallbackData,prefix='prod'):
    item_id: int

class BuyCD(CallbackData,prefix='buy'):
    item_id: int

class ItemsPageCD(CallbackData,prefix='items_page'):
    category_id: int
    page: int

# class PayCheckCD(CallbackData,prefix='chek_pay'):
#     invoice_id: int
#     item_id: int


def keyboard_categories(categories: list, is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for cat in categories:
        kb.button(text=cat.name,callback_data=CategoryCD(category_id=cat.id).pack())

    if is_admin:
        kb.button(text="📦 Создать категорию",callback_data="create_category")
        
    kb.adjust(1)
    return kb.as_markup()


def sub_categories_kb(category_id: int, sub_categories: list, is_admin: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for sub in sub_categories:
        kb.button(text=sub.name,callback_data=SubCategoryCD(sub_category_id=sub.id).pack())

    if is_admin:
        kb.button(text="❌ Удалить категорию", callback_data=f"del_cat:{category_id}")
        kb.button(text="📦 Создать подкатегорию", callback_data=f"create_sub_cat:{category_id}")

    kb.button(text="🔙 НАЗАД", callback_data="back_to_categories")

    kb.adjust(1)
    return kb.as_markup()

def item_card_keyboard(item_id: int, category_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="💳 Купить", callback_data=f"buy_item:{item_id}")
    kb.button(text="🔙 Назад к списку",callback_data=CategoryCD(category_id=category_id).pack())


    if is_admin:
        kb.button(text="✏️ Редактировать данные", callback_data=f"admin_edit_data:{item_id}")
        kb.button(text="✏️ Редактировать стоимость",callback_data=f"admin_edit_price:{item_id}")

        kb.button(text="❌ Удалить товар", callback_data=f"admin_delete_item:{item_id}")
        

    kb.adjust(1)
    return kb.as_markup()

def confirm_buy_item(item_id: int, category_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="✅ Купить", callback_data=BuyCD(item_id=item_id).pack())
    kb.button(text="❌ Отмена",callback_data=CategoryCD(category_id=category_id).pack())

    kb.adjust(1)

    return kb.as_markup()
#категории товаров для админа
def category_admin(categories: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for cat in categories:
        kb.button(text=cat.name, callback_data=f"admin_cat:{cat.id}")
    kb.button(text="❌ Отмена", callback_data="admin_cancel_upload")

    kb.adjust(2)
    return kb.as_markup()

def sub_category_admin(sub_categories: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for sub in sub_categories:
        kb.button(text=sub.name, callback_data=f"admin_sub_cat:{sub.id}")
        
    kb.button(text="❌ Отмена", callback_data="admin_cancel_upload")
    
    kb.adjust(2)
    return kb.as_markup()

def items_pagination_keyboards(page: int, total_page: int, category_id: int, items: list, is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for item in items:
        kb.row(
            InlineKeyboardButton(
                text=f"💎 {item.title} | {item.price}₽",callback_data=ItemsCD(item_id=item.id).pack()
            )
        )
    pagination = []

    if page > 1:
        pagination.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=ItemsPageCD(
                    category_id=category_id,
                    page=page - 1
                ).pack()
            )
        )

    pagination.append(
        InlineKeyboardButton(
            text=f"{page}/{total_page}",
            callback_data="ignore"
        )
    )

    if page < total_page:
        pagination.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=ItemsPageCD(
                    category_id=category_id,
                    page=page + 1
                ).pack()
            )
        )


    kb.row(*pagination)

    kb.row(
        InlineKeyboardButton(
            text="🔙 МЕНЮ",
            callback_data="back_to_categories"
        )
    )
    if is_admin:
        kb.row(
            InlineKeyboardButton(
            text="❌ Удалить подкатегорию",
            callback_data=f"delete_sub_cat:{category_id}"
        )
    )

    return kb.as_markup()

#Создание клавиатуры для проверки оплаты

# def check_pay_keyboard(invoice: dict,item_id: int) -> InlineKeyboardMarkup:
#     kb = InlineKeyboardBuilder()

#     kb.button(text="Оплатить",url=invoice["bot_invoice_url"])
#     kb.button(text="Проверить оплату",callback_data=PayCheckCD(invoice_id=invoice["invoice_id"],item_id=item_id))

#     kb.adjust(1)

#     return kb.as_markup()

# Клавиатура для поплнения баланса

def top_up_balance_crypto_kb(amount: int, invoice: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    invoice_id = invoice.get('invoice_id')
    kb.button(text=f"🪪 Оплатить {amount} ₽",url=invoice["bot_invoice_url"])
    kb.button(text="Проверить оплату",callback_data=f"check_pay_crypto:{invoice_id}")
    kb.button(text="Отменить оплату", callback_data=f"cancel_crypto_payments:{invoice_id}")
    kb.adjust(1)

    return kb.as_markup()

#кнопка отмены для отправки рассылки всем пользователям

def cancel_mailing_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить рассылку",callback_data="cancel_mailing")

    return kb.as_markup()

#кнопка генерации промокода
def generation_code_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✨Сгенерировать✨",callback_data="gen_code")
    kb.button(text="❌ Отмена",callback_data="admin_cancel_promocode")

    kb.adjust(1)
    return kb.as_markup()

#клавиатура проверки подписки на канал

def sub_channel_kb():
    kb = InlineKeyboardBuilder()

    kb.button(text="📢 Подписаться на канал", url=f"{settings.CHANNEL_URL}")
    kb.button(text="🔄 Проверить", callback_data="sub_check")

    kb.adjust(1)
    return kb.as_markup()


#клавиатура для массовой покупки (кнопки 1шт | 5 шт | ввести свое кол-во)

def mass_loading_kb(stock: int, mass_product_id, sub_category_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    buttons_count = 0

    if stock > 0:
        kb.button(text="1", callback_data=f"buy_mass:{mass_product_id}:1")
        buttons_count += 1
    if stock >= 5:
        kb.button(text="5", callback_data=f"buy_mass:{mass_product_id}:5")
        buttons_count += 1
    if stock >= 10:
        kb.button(text="10", callback_data=f"buy_mass:{mass_product_id}:10")
        buttons_count += 1

    if stock > 0:
        kb.button(
            text="Другое количество",
            callback_data=f"enter_mass:{mass_product_id}",
        )

    kb.button(text="🔙 НАЗАД", callback_data="back_to_categories")
    if is_admin:
        kb.button(text="🗑 Удалить лот", callback_data=f"delete_mass_lot:{sub_category_id}")
        kb.button(text="✏️ Редактировать стоимость", callback_data=f"mass_edit_price:{mass_product_id}")
    if stock > 0:
        kb.adjust(buttons_count,1,1)
    else:
        kb.adjust(1)

    return kb.as_markup()

#подтверждение массовой покупки
def confirm_mass_buy_kb(product_id: int, count: int) -> InlineKeyboardMarkup:
  kb = InlineKeyboardBuilder()

  kb.button(
      text=f"✅ Да, купить ({count} шт.)",
      callback_data=f"confirm_mass:{product_id}:{count}",
  )
  kb.button(text="❌ Отмена", callback_data="back_to_categories")

  kb.adjust(1)

  return kb.as_markup()

#клавиатура для поиска заказов пользователей
def orders_user_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(text="📦 Найти заказ по ID", callback_data="search_by_order_id")
    kb.button(text="👤 Найти пользователя (ID / @username)", callback_data="search_by_user_orders")
    kb.button(text="❌ Отмена", callback_data="cancel_search_order")

    kb.adjust(2,1)

    return kb.as_markup()

