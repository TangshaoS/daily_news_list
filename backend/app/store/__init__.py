"""
Storage module - persists news metadata to SQLite.
"""
from .database import NewsDatabase, init_database

__all__ = ["NewsDatabase", "init_database"]
