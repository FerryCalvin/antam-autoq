from sqlalchemy import Column, Integer, String, Boolean
from .base import Base

class Profile(Base):
    """
    Model representing user profiles for booking.
    """
    __tablename__ = 'profiles'

    id = Column(Integer, primary_key=True, index=True)
    nama_lengkap = Column(String, nullable=False)
    nik = Column(String, nullable=False, unique=True)
    no_hp = Column(String, nullable=False)
    email = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
