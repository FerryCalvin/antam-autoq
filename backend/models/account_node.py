from sqlalchemy import Column, Integer, String, Boolean
from backend.models.base import Base

class AccountNode(Base):
    """
    Model storing configurations for each bot instance (Node).
    """
    __tablename__ = 'account_nodes'

    id = Column(Integer, primary_key=True, index=True)
    nama_lengkap = Column(String, nullable=False)
    nik = Column(String, index=True, nullable=False)
    no_hp = Column(String, nullable=False)
    email = Column(String, nullable=False)
    password = Column(String, nullable=False)
    target_location = Column(String, nullable=False) # e.g. SUB-01
    proxy = Column(String, nullable=True) # Optional HTTP proxy
    is_active = Column(Boolean, default=False) # Status of the Bot Note
    status_message = Column(String, default="Ready") # Live status like 'Stopped', 'Hunting'
