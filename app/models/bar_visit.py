from sqlalchemy import Column, Integer, Text, Date, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class BarVisit(Base):
    __tablename__ = "bar_visits"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    bar_id     = Column(Integer, ForeignKey("hifi_bars.id", ondelete="CASCADE"), nullable=False, index=True)
    date       = Column(Date, nullable=False)
    drinks     = Column(Text, nullable=True)   # que tomo
    notes      = Column(Text, nullable=True)   # notas de la visita
    score      = Column(Integer, nullable=True)  # 1-10
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    bar = relationship("HifiBar", back_populates="visits")
