"""
Services package for business logic.
"""
from app.services.chat_service import process_chat_message
# 🌟 v2.0: pdf_service 已简化，不再提供 run_opendataloader
from app.services.pdf_service import process_pdf_async
from app.services.document_service import DocumentService

__all__ = [
    "process_chat_message",
    "process_pdf_async",
    "DocumentService",
]
