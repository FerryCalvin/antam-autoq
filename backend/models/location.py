from sqlalchemy import Column, Integer, String, Boolean
from .base import Base

class TargetLocation(Base):
    """
    Model representing the target locations / branches for the bot to monitor.
    """
    __tablename__ = 'target_locations'

    id = Column(Integer, primary_key=True, index=True)
    nama_cabang = Column(String, nullable=False)
    api_location_id = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
