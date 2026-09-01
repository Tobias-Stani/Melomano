from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class SavedSetlist(Base):
    __tablename__ = "saved_setlists"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name             = Column(Text, nullable=False)
    content          = Column(Text, nullable=False)
    duration_minutes = Column(Integer, nullable=True)
    num_tracks       = Column(Integer, nullable=True)
    user_context     = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
