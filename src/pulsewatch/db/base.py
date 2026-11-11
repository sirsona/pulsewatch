"""Declarative base shared by the ORM models and Alembic."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all PulseWatch ORM models."""
