from sqlalchemy import Column, Integer, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class FormatType(Base):
    __tablename__ = "format_types"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(Text, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
