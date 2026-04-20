"""
Pydantic Schemas for chat-related API endpoints.
"""
from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    """Request schema for chat endpoint"""
    message: str
    username: str = "anonymous"
    document_path: Optional[str] = None


class ChatResponse(BaseModel):
    """Response schema for chat endpoint"""
    reply: str
    success: bool = True


class ChatStreamRequest(BaseModel):
    """Request schema for streaming chat endpoint"""
    message: str
    username: str = "anonymous"
    document_path: Optional[str] = None
    session_id: Optional[str] = None
