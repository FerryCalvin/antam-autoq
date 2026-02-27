import asyncio
import os
from sqlalchemy.future import select

# Ensure project root is in PYTHONPATH for direct execution
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.database import engine, AsyncSessionLocal
from models import Base, Profile, TargetLocation, BotConfig

async def seed_data():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as session:
        # Check if Profile already exists
        result = await session.execute(select(Profile).filter_by(nik="1234567890123456"))
        existing_profile = result.scalars().first()
        
        if not existing_profile:
            profile = Profile(
                nama_lengkap="Nama Lengkap",
                nik="1234567890123456",
                no_hp="081234567890",
                email="user@example.com",
                is_active=True
            )
            session.add(profile)
            
        # Check if Location already exists
        result = await session.execute(select(TargetLocation).filter_by(api_location_id="SUB-01"))
        existing_loc = result.scalars().first()
        
        if not existing_loc:
            location = TargetLocation(
                nama_cabang="Butik Emas Surabaya",
                api_location_id="SUB-01",
                is_active=True
            )
            session.add(location)
            
        # Check if BotConfig exists
        result = await session.execute(select(BotConfig))
        existing_config = result.scalars().first()
        
        if not existing_config:
            config = BotConfig(
                telegram_chat_id="",
                telegram_bot_token="",
                request_delay_seconds=5
            )
            session.add(config)
            
        await session.commit()
        
    print("Database seeding completed successfully.")

if __name__ == "__main__":
    asyncio.run(seed_data())
