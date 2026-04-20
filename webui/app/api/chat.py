"""
Chat API Router - Handles all chat-related endpoints
🎯 Architecture: Uses unified config from core.config
"""
import json
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, ChatResponse, ChatStreamRequest
from app.services.chat_service import process_chat_message
from app.core.config import settings  # 🌟 引入統一配置

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint for processing user messages.
    🌟 使用 Service 处理，启用 Fallback 逻辑
    """
    try:
        reply = await process_chat_message(
            user_message=request.message,
            username=request.username,
            document_path=request.document_path,
            session_id=request.session_id
        )
        return ChatResponse(reply=reply, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream_endpoint(request: ChatStreamRequest):
    """
    Streaming chat endpoint for real-time responses.
    Forwards requests to Gateway and streams back the LLM response.
    """
    try:
        async def forward_stream():
            async with httpx.AsyncClient(timeout=120.0) as client:
                try:
                    # 🌟 直接使用 settings.GATEWAY_URL
                    async with client.stream(
                        "POST", 
                        f"{settings.GATEWAY_URL}/api/stream", 
                        json={
                            "message": request.message,
                            "username": request.username,
                            "document_path": request.document_path,
                            "session_id": request.session_id
                        }
                    ) as response:
                        async for chunk in response.aiter_bytes():
                            yield chunk
                except Exception as e:
                    yield f"data: {{\"error\": \"無法連線至 AI 引擎：{str(e)}\"}}\n\n".encode('utf-8')
        
        return StreamingResponse(forward_stream(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))