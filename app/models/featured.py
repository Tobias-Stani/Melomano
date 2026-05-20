from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class FeaturedItem(Base):
    __tablename__ = "featured_items"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    type       = Column(String(10), nullable=False)   # 'album' | 'concert'
    item_id    = Column(Integer, nullable=False)
    slot       = Column(Integer, nullable=False)       # 1-5 albums, 1-3 concerts
    created_at = Column(DateTime(timezone=True), server_default=func.now())
