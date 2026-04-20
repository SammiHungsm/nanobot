"""
Pydantic Schemas for document-related API endpoints.
"""
from pydantic import BaseModel
from typing import Optional, List


class DocumentBase(BaseModel):
    """Base document schema"""
    filename: str
    path: str


class DocumentCreate(DocumentBase):
    """Schema for creating a new document"""
    uploader: str = "System"
    size: int = 0


class DocumentStatus(BaseModel):
    """Schema for document processing status"""
    document_id: str
    filename: str
    status: str  # pending, queued, processing, completed, failed
    progress: float = 0.0
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    page_count: Optional[int] = None


class DocumentListResponse(BaseModel):
    """Response schema for document list endpoint"""
    documents: List[dict]
    success: bool = True


class DocumentUploadResponse(BaseModel):
    """Response schema for file upload endpoint"""
    success: bool
    message: str
    files: List[dict]


class ProcessingLogResponse(BaseModel):
    """Response schema for processing logs"""
    logs: List[dict]
    success: bool = True


class QueueStatusResponse(BaseModel):
    """Response schema for queue status"""
    total_documents: int
    pending_count: int
    queued_count: int
    processing_count: int
    completed_count: int
    failed_count: int
    queue_size: int
    is_running: bool
