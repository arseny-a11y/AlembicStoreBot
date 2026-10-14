from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

def create_keyboard_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:

    kb = ReplyKeyboardBuilder()

    kb.add(
        KeyboardButton(text='Каталог товаров 🛒'),
        KeyboardButton(text='Профиль 👤'),
        KeyboardButton(text='Пополнить баланс 📥'),
        KeyboardButton(text='ℹ️ О SUP SHOP'),
        KeyboardButton(text='🆘 Поддержка')
    )

    if is_admin:
        kb.add(KeyboardButton(text="🤖 Админка"))
        
    kb.adjust(1,2)
    return kb.as_markup(resize_keyboard=True)

#меню администатора 
def admin_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(
        KeyboardButton(text="📥 Загрузить (.txt) файл товаров"),
        KeyboardButton(text="📊 Статистика"),
        KeyboardButton(text="📦 Управление товарами"),
        KeyboardButton(text="👤 Рассылка"),
        KeyboardButton(text="🎫 Создать промокод"),
        KeyboardButton(text="💵 Управление балансом"),
        KeyboardButton(text="🔍 Поиск заказов"),
        KeyboardButton(text="⭕ Бан пользователя")
    )

    
    kb.adjust(2,2)
    return kb.as_markup(resize_keyboard=True)