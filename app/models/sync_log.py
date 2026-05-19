from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id          = Column(Integer, primary_key=True, index=True)
    status      = Column(String(20), nullable=False)  # "success", "error", "running"
    source      = Column(String(50), default="discogs")
    added       = Column(Integer, default=0)
    updated     = Column(Integer, default=0)
    total       = Column(Integer, default=0)
    message     = Column(Text, nullable=True)
    started_at  = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
