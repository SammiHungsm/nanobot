"""
Chat API Router - Handles all chat-related endpoints
"""
from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import process_chat_message

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint for processing user messages.
    """
    try:
        reply_text = await process_chat_message(
            request.message,
            request.username,
            request.document_path
        )
        return ChatResponse(reply=reply_text, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
