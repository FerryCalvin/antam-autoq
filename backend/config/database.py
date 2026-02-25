import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Setup Database path relative to this file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "antam_bot.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# Create async engine for SQLite
engine = create_async_engine(DATABASE_URL, echo=False)

# Create session maker
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    """Dependency to get the database session"""
    async with AsyncSessionLocal() as session:
        yield session
