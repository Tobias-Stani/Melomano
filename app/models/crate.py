from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Crate(Base):
    __tablename__ = "crates"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name       = Column(Text, nullable=False)
    position   = Column(Integer, default=0, nullable=False)
    color      = Column(Text, nullable=True)
    height     = Column(Integer, default=160, nullable=False, server_default="160")
    col_span   = Column(Integer, default=1,   nullable=False, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
