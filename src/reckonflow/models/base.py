"""I define the shared SQLAlchemy declarative base

Every mapped table inherits from Base so Alembic and metadata stay in sync
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """I am the parent class for all ReckonFlow ORM models"""
