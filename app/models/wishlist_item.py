from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("wishlist_categories.id"), nullable=True, index=True)
    discogs_id  = Column(Integer, nullable=True)
    title       = Column(Text, nullable=False)
    artist      = Column(Text, nullable=False)
    year        = Column(Integer, nullable=True)
    genre       = Column(Text, nullable=True)
    label       = Column(Text, nullable=True)
    cover_url   = Column(Text, nullable=True)
    discogs_url = Column(Text, nullable=True)
    format_type = Column(Text, nullable=True)
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("WishlistCategory", back_populates="items")
