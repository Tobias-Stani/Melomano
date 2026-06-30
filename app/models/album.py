from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean, Float, ForeignKey, UniqueConstraint

from sqlalchemy.sql import func
from app.database import Base


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        UniqueConstraint("discogs_id", "user_id", name="uq_album_discogs_user"),
    )

    id              = Column(Integer, primary_key=True, index=True)

    # Propietario
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Metadatos musicales
    title           = Column(Text, nullable=False)
    artist          = Column(Text, nullable=False)
    year            = Column(Integer, nullable=True)
    genre           = Column(Text, nullable=True)
    label           = Column(Text, nullable=True)
    cover_url       = Column(Text, nullable=True)
    formats         = Column(Text, nullable=True)

    # Origen
    discogs_id      = Column(Integer, nullable=True, index=True)
    discogs_url     = Column(Text, nullable=True)

    # Batea fisica donde esta guardado
    crate_id        = Column(Integer, ForeignKey("crates.id"), nullable=True, index=True)
    crate_position  = Column(Integer, nullable=True, default=0)

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
    deleted_at      = Column(DateTime(timezone=True), nullable=True)

    # Mercado Discogs (cacheado para no pegarle a la API en cada mensaje del chat)
    discogs_lowest_price = Column(Float, nullable=True)
    discogs_num_for_sale = Column(Integer, nullable=True)
    discogs_have         = Column(Integer, nullable=True)
    discogs_want         = Column(Integer, nullable=True)
    discogs_extra_synced_at = Column(DateTime(timezone=True), nullable=True)
