from sqlalchemy import Column, Integer, Text, String, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# Usuarios con los que se comparte una película (aparece en la colección de todos)
movie_shares = Table(
    "movie_shares", Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id",  Integer, ForeignKey("users.id",  ondelete="CASCADE"), primary_key=True),
)

FORMATS = {
    "dvd":            "DVD",
    "bluray":         "Blu-ray",
    "dvd_bootleg":    "DVD bootleg",
    "bluray_bootleg": "Blu-ray bootleg",
}


class Movie(Base):
    __tablename__ = "movies"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tmdb_id        = Column(Integer, nullable=True)
    title          = Column(Text, nullable=False)
    original_title = Column(Text, nullable=True)
    year           = Column(Integer, nullable=True)
    director       = Column(Text, nullable=True)
    genres         = Column(Text, nullable=True)
    runtime        = Column(Integer, nullable=True)
    overview       = Column(Text, nullable=True)
    poster_url     = Column(Text, nullable=True)
    backdrop_url   = Column(Text, nullable=True)
    format_type    = Column(String(20), nullable=False, default="dvd")
    edition_photo  = Column(Text, nullable=True)  # foto propia de la caja (data URL)
    notes          = Column(Text, nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    owner       = relationship("User", foreign_keys=[user_id])
    shared_with = relationship("User", secondary=movie_shares, order_by="User.username")

    def can_edit(self, user) -> bool:
        return user.id == self.user_id or user in self.shared_with
