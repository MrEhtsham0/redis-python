from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.postgres_connection import Base
from sqlalchemy import ForeignKey
from datetime import datetime
from sqlalchemy import DateTime,Float


class User(Base):
    __tablename__ = "users"
    id:Mapped[int] = mapped_column(Integer, primary_key=True,index=True)
    username:Mapped[str] = mapped_column(String, unique=True)
    email:Mapped[str] = mapped_column(String, unique=True)
    password:Mapped[str] = mapped_column(String)
    is_active:Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser:Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified:Mapped[bool] = mapped_column(Boolean, default=False)

class Orders(Base):
    __tablename__ = "orders"
    id:Mapped[int] = mapped_column(Integer, primary_key=True,index=True)
    user_id:Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    order_date:Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    total_amount:Mapped[float] = mapped_column(Float)
    status:Mapped[str] = mapped_column(String, default="pending")