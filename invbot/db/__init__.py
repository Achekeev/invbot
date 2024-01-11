import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import settings

# setup database logging
logging.getLogger('sqlalchemy.engine').setLevel(
    getattr(logging, settings.SQL_LOG_LEVEL.upper())
)
logging.getLogger('aiosqlite').setLevel(
    getattr(logging, settings.SQL_LOG_LEVEL.upper())
)

engine = create_async_engine(settings.DB_URL)
session_maker = async_sessionmaker(engine, expire_on_commit=False)

SessionMaker = async_sessionmaker[AsyncSession]
