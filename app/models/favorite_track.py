from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class FavoriteTrack(Base):
    __tablename__ = "favorite_tracks"
    __table_args__ = (
        UniqueConstraint("user_id", "album_id", name="uq_favorite_track_user_album"),
    )

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    album_id   = Column(Integer, ForeignKey("albums.id"), nullable=False, index=True)
    track_pos  = Column(String(10), nullable=False)
    track_title = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
