import asyncio, getpass
from app.core.security import hash_password
from sqlalchemy import select
from app.db.session import async_session
from app.db.models import MfgUser, UserRole

async def main():
    login = input("Admin login: ").strip()
    pwd = getpass.getpass("Admin password: ")
    async with async_session() as s:
        exists = (await s.execute(select(MfgUser).where(MfgUser.login == login))).scalar_one_or_none()
        if exists:
            print("User exists")
            return
        u = MfgUser(login=login, password_hash=hash_password(pwd), role=UserRole.admin, is_active=True)
        s.add(u); await s.commit(); print("Admin created")

asyncio.run(main())
