"""
API package for FastAPI routers.

🌟 Architecture Improvements:
- Uses Dependency Injection (no init_document_service needed)
- Includes database_router for direct PostgreSQL access
"""
from app.api.chat import router as chat_router
from app.api.document import router as document_router
from app.api.database import router as database_router

__all__ = [
    "chat_router",
    "document_router",
    "database_router",
]