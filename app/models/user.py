from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    username      = Column(String(50), unique=True, nullable=False, index=True)
    display_name  = Column(String(100), nullable=True)
    bio           = Column(Text, nullable=True)
    avatar        = Column(Text, nullable=True)   # base64
    password_hash = Column(Text, nullable=False)
    is_admin      = Column(Boolean, default=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
