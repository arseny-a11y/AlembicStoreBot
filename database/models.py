from datetime import datetime
from decimal import Decimal
from sqlalchemy import func, BigInteger, Numeric, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, relationship
from typing import Annotated
from enum import Enum

class Base(DeclarativeBase):
    def __repr__(self):
        values = ", ".join(
            f"{col}={getattr(self,col)!r}"
            for col in self.__table__.columns.keys()
        )
        return f"{self.__class__.__name__}({values})"



all_id = Annotated[int,mapped_column(primary_key=True,autoincrement=True)]
user_tg_id = Annotated[int, mapped_column(BigInteger)]
time_now = Annotated[datetime,mapped_column(server_default=func.now())]

class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True,autoincrement=True)
    tg_id: Mapped[int] = mapped_column(unique=True,index=True)
    username: Mapped[str | None]
    full_name: Mapped[str]
    registered_at: Mapped[time_now]
    balance: Mapped[Decimal] = mapped_column(Numeric(10,2),default=Decimal('0.00'))



class Categories(Base):
    __tablename__ = 'categories'

    id: Mapped[all_id]
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)


class SubCategories(Base):
    __tablename__ = 'sub_categories'

    id: Mapped[all_id]
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)


class Products(Base):
  __tablename__ = "products"

  id: Mapped[all_id]
  subcategory_id: Mapped[int] = mapped_column(
      ForeignKey("sub_categories.id", ondelete="CASCADE")
  )
  name: Mapped[str]
  description: Mapped[str] = mapped_column(Text)
  price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
  created_at: Mapped[time_now]



class Items(Base):
    __tablename__ = 'items'

    id: Mapped[all_id]
    category_id: Mapped[int] = mapped_column(ForeignKey('sub_categories.id', ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(
      ForeignKey("products.id", ondelete="CASCADE"), nullable=True, default=None
    )
    title: Mapped[str | None] = mapped_column(nullable=True, default=None)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10,2), nullable=True, default=None)
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(10,2), nullable=False)
    data: Mapped[str] = mapped_column(Text)
    is_sold: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[time_now]

class Orders(Base):
    __tablename__ = 'orders'

    id: Mapped[all_id]
    user_id: Mapped[user_tg_id] = mapped_column(ForeignKey('users.id'))
    name: Mapped[str] = mapped_column(nullable=False, default="Товар")
    item_id: Mapped[int] = mapped_column(ForeignKey('items.id'))
    price: Mapped[Decimal] = mapped_column(Numeric(10,2))
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(10,2), nullable=False)
    item_data: Mapped[str]
    purchased_at: Mapped[time_now]
    refund: Mapped[bool] = mapped_column(default=False)

class Payments(Base):
    __tablename__ = 'payments'

    id: Mapped[all_id]
    user_id: Mapped[user_tg_id] = mapped_column(BigInteger, ForeignKey('users.id'))
    invoice_id: Mapped[int] = mapped_column(unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10,2))
    payment_system: Mapped[str]
    status: Mapped[str] = mapped_column(default='pending')
    created_at: Mapped[time_now]


#таблицы для реализации промокодов:

class PromoCode(Base):
    __tablename__ = "promocodes"

    id: Mapped[all_id]
    code: Mapped[str] = mapped_column(unique=True, index=True) #сам промокод
    max_uses: Mapped[int] # кол-во использований
    current_uses: Mapped[int] = mapped_column(default=0)
    reward_amount: Mapped[int] #сумма активации
    create_at: Mapped[time_now] #дата создания

class PromoUsage(Base):
    __tablename__ = "promo_usage"

    id: Mapped[all_id]
    promo_id = mapped_column(ForeignKey("promocodes.id"))
    tg_id: Mapped[int] = mapped_column(index=True) # ID пользователя активировавший промокод
    used_at: Mapped[time_now]