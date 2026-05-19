from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean, Float
from sqlalchemy.sql import func
from app.database import Base


class Album(Base):
    __tablename__ = "albums"

    id              = Column(Integer, primary_key=True, index=True)

    # Metadatos musicales
    title           = Column(Text, nullable=False)
    artist          = Column(Text, nullable=False)
    year            = Column(Integer, nullable=True)
    genre           = Column(Text, nullable=True)
    label           = Column(Text, nullable=True)
    cover_url       = Column(Text, nullable=True)
    formats         = Column(Text, nullable=True)

    # Origen
    discogs_id      = Column(Integer, unique=True, nullable=True, index=True)
    discogs_url     = Column(Text, nullable=True)

    # Estado en la coleccion
    owned           = Column(Boolean, default=False)
    listened        = Column(Boolean, default=False)
    wishlist        = Column(Boolean, default=False)
    format_type     = Column(Text, nullable=True)

    # Valoracion personal
    score           = Column(Integer, nullable=True)   # 1-10
    review          = Column(Text, nullable=True)
    listened_date   = Column(Date, nullable=True)

    # Timestamps
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())
    synced_at       = Column(DateTime(timezone=True), nullable=True)  # ultima sync con discogs
