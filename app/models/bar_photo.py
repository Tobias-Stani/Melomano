from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BarPhoto(Base):
    __tablename__ = "bar_photos"

    id         = Column(Integer, primary_key=True, index=True)
    bar_id     = Column(Integer, ForeignKey("hifi_bars.id", ondelete="CASCADE"), nullable=False, index=True)
    data       = Column(Text, nullable=False)   # base64
    mime_type  = Column(Text, default="image/jpeg")
    caption    = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    bar = relationship("HifiBar", back_populates="photos")
