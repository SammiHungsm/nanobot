"""
API package for FastAPI routers.
"""
from app.api.chat import router as chat_router
from app.api.document import router as document_router, init_document_service

__all__ = [
    "chat_router",
    "document_router",
    "init_document_service",
]
