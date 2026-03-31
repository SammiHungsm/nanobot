"""
Chat API Router - Handles all chat-related endpoints
"""
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, ChatResponse, ChatStreamRequest
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


@router.post("/stream")
async def chat_stream_endpoint(request: ChatStreamRequest):
    """
    Streaming chat endpoint for real-time responses.
    """
    try:
        async def generate():
            # For now, use the regular chat processor
            # TODO: Implement proper streaming in chat_service
            reply_text = await process_chat_message(
                request.message,
                request.username,
                request.document_path,
                request.session_id
            )
            
            # Send as SSE-like stream
            yield f"data: {json.dumps({'content': reply_text})}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
