import asyncio
import logging
from typing import List

from sqlalchemy.future import select
from config.database import AsyncSessionLocal
from models import TargetLocation, Profile, BotConfig, BookingLog
from services.antam_api import check_quota, submit_booking
from services.telegram_bot import send_telegram_alert

logger = logging.getLogger(__name__)

async def get_active_locations(session) -> List[TargetLocation]:
    result = await session.execute(select(TargetLocation).filter_by(is_active=True))
    return list(result.scalars().all())

async def get_active_profiles(session) -> List[Profile]:
    result = await session.execute(select(Profile).filter_by(is_active=True))
    return list(result.scalars().all())

async def get_bot_config(session) -> BotConfig | None:
    result = await session.execute(select(BotConfig))
    return result.scalars().first()

async def run_tracker_and_sniper(target_date: str):
    """
    Main loop iteration:
    1. Checks quota for active locations.
    2. If quota > 0, fires sniper for active profiles.
    3. Logs the result.
    """
    async with AsyncSessionLocal() as session:
        locations = await get_active_locations(session)
        profiles = await get_active_profiles(session)
        config = await get_bot_config(session)
        
        if not locations or not profiles:
            logger.warning("No active locations or profiles found.")
            return

        for location in locations:
            logger.info(f"Checking quota for {location.nama_cabang} ({location.api_location_id}) on {target_date}...")
            quota = await check_quota(location.api_location_id, target_date)
            
            logger.info(f"Quota for {location.api_location_id}: {quota}")
            
            if quota > 0:
                # Notify Telegram
                msg = f"🟢 SLOT OPEN! Quota: {quota} at {location.nama_cabang} for {target_date}.\nExecuting Sniper..."
                logger.info(msg)
                if config:
                    await send_telegram_alert(config.telegram_bot_token, config.telegram_chat_id, msg)
                
                # Execute sniper for all active profiles
                for profile in profiles:
                    logger.info(f"Submitting booking for {profile.nama_lengkap} at {location.nama_cabang}...")
                    result = await submit_booking(profile, location, target_date)
                    
                    status = "SUCCESS" if result.get("success") else "FAILED"
                    
                    # Log result to database
                    log_entry = BookingLog(
                        profile_id=profile.id,
                        location_id=location.id,
                        target_date=target_date,
                        status=status,
                        response_payload=str(result)
                    )
                    session.add(log_entry)
                    
                    # Notify result
                    res_msg = f"Sniper Result for {profile.nama_lengkap} at {location.nama_cabang}:\nUser Status: {status}\nDetails: {result.get('error') or result.get('status_code')}"
                    logger.info(res_msg)
                    if config:
                        await send_telegram_alert(config.telegram_bot_token, config.telegram_chat_id, res_msg)
                        
                await session.commit()

async def start_scheduler(target_date: str):
    """
    Continuously runs the tracker logic with the configured delay.
    """
    logger.info("Starting Tracker Scheduler...")
    
    while True:
        try:
            # Refresh delay from DB each loop iteration
            async with AsyncSessionLocal() as session:
                config = await get_bot_config(session)
                delay = config.request_delay_seconds if config else 60
                
            await run_tracker_and_sniper(target_date)
            
            logger.info(f"Sleeping for {delay} seconds before next check...")
            await asyncio.sleep(delay)
            
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            await asyncio.sleep(10) # Fallback delay to avoid rapid looping on failures
