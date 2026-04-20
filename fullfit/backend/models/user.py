import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String

from database import Base


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    WORKER = "WORKER"
    SELLER = "SELLER"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
