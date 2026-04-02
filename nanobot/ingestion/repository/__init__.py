"""
Repository Module - 數據庫操作層

集中所有 PostgreSQL 操作。
"""

from .db_client import DBClient

__all__ = ["DBClient"]