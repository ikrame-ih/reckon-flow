"""Shared SQLAlchemy declarative base for Alembic and metadata sync"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Parent class for all ReckonFlow ORM models"""
