from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from .base import Base

class BookingLog(Base):
    """
    Model storing all attempts or final booking statuses.
    """
    __tablename__ = 'booking_logs'

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey('profiles.id'), nullable=False)
    location_id = Column(Integer, ForeignKey('target_locations.id'), nullable=False)
    target_date = Column(String, nullable=False)
    status = Column(String, nullable=False)
    response_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
