"""
API package for FastAPI routers.
"""
from app.api.chat import router as chat_router
from app.api.document import router as document_router, init_document_service
from app.api.database import router as database_router

__all__ = [
    "chat_router",
    "document_router",
    "database_router",
    "init_document_service",
]
