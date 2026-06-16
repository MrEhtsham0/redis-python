"""Seed the database with fake users and orders."""

import asyncio
import random
import uuid

from faker import Faker

from app.db.postgres_connection import create_tables, dispose_db, get_sessionmaker, init_db
from app.models.user_models import Orders, User

fake = Faker()

USER_COUNT = 100
ORDER_COUNT = 100
ORDER_STATUSES = ("pending", "processing", "shipped", "delivered", "cancelled")


def _unique_username() -> str:
    return f"{fake.user_name()}_{uuid.uuid4().hex[:8]}"


def _unique_email() -> str:
    return f"{uuid.uuid4().hex[:8]}_{fake.email()}"


async def create_fake_users(session) -> list[int]:
    users: list[User] = []
    for _ in range(USER_COUNT):
        user = User(
            username=_unique_username(),
            email=_unique_email(),
            password=fake.password(),
            is_active=fake.boolean(),
            is_superuser=fake.boolean(),
            is_verified=fake.boolean(),
        )
        session.add(user)
        users.append(user)

    await session.flush()
    user_ids = [user.id for user in users]
    await session.commit()
    return user_ids


async def create_fake_orders(session, user_ids: list[int]) -> None:
    if not user_ids:
        raise RuntimeError("No users found — create users before orders.")

    for _ in range(ORDER_COUNT):
        order = Orders(
            user_id=random.choice(user_ids),
            order_date=fake.date_time(),
            total_amount=round(fake.pyfloat(min_value=1, max_value=1000), 2),
            status=random.choice(ORDER_STATUSES),
        )
        session.add(order)

    await session.commit()


async def main() -> None:
    await init_db()
    await create_tables()

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        user_ids = await create_fake_users(session)
        await create_fake_orders(session, user_ids)

    print(f"Seeded {USER_COUNT} users and {ORDER_COUNT} orders.")
    await dispose_db()


if __name__ == "__main__":
    asyncio.run(main())
