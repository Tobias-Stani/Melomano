from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class HifiBar(Base):
    __tablename__ = "hifi_bars"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(200), nullable=False)
    address     = Column(Text, nullable=True)
    city        = Column(String(100), nullable=True)
    country     = Column(String(100), nullable=True)
    maps_url    = Column(Text, nullable=True)      # Google Maps share URL
    description = Column(Text, nullable=True)
    cover_url   = Column(Text, nullable=True)      # base64 o URL
    banner_url  = Column(Text, nullable=True)      # imagen de fondo ancha (header)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    visits = relationship("BarVisit", back_populates="bar",
                          cascade="all, delete-orphan", order_by="BarVisit.date.desc()")
    photos = relationship("BarPhoto", back_populates="bar",
                          cascade="all, delete-orphan", order_by="BarPhoto.created_at")
