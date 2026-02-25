from sqlalchemy import Column, Integer, String
from .base import Base

class BotConfig(Base):
    """
    Model storing dynamic configuration for the bot (e.g. Telegram tokens).
    """
    __tablename__ = 'bot_configs'

    id = Column(Integer, primary_key=True, index=True)
    telegram_chat_id = Column(String, nullable=True)
    telegram_bot_token = Column(String, nullable=True)
    request_delay_seconds = Column(Integer, default=5)
