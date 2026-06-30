from sqlalchemy import Column, Integer, Text, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class WishlistCategory(Base):
    __tablename__ = "wishlist_categories"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name       = Column(Text, nullable=False)
    color      = Column(String(20), nullable=False, default="#c49268")
    position   = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("WishlistItem", back_populates="category", cascade="save-update, merge")
