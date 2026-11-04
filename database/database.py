from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config.config import settings
from database.models import Base

async_engine = create_async_engine(url=settings.DATABASE_URL_aiosqlite,echo=False)
async_session_factory = async_sessionmaker(async_engine,expire_on_commit=False)

async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)