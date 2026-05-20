from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Concert(Base):
    __tablename__ = "concerts"

    id          = Column(Integer, primary_key=True, index=True)

    artist      = Column(String(255), nullable=False)
    date        = Column(Date, nullable=False)
    venue       = Column(String(255), nullable=True)
    city        = Column(String(100), nullable=True)
    country     = Column(String(100), nullable=True)
    tour_name   = Column(String(200), nullable=True)

    # Experiencia personal
    score       = Column(Integer, nullable=True)   # 1-10
    review      = Column(Text, nullable=True)
    setlist     = Column(Text, nullable=True)      # canciones que tocaron
    highlights  = Column(Text, nullable=True)      # momento especial
    cover_url   = Column(Text, nullable=True)      # foto del show o del artista
    banner_url  = Column(Text, nullable=True)      # imagen de fondo ancha (header)

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    photos = relationship("ConcertPhoto", back_populates="concert",
                          cascade="all, delete-orphan", order_by="ConcertPhoto.created_at")
