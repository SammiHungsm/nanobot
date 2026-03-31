"""
Chat API Router - Handles all chat-related endpoints
"""
import json
import os
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, ChatResponse, ChatStreamRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Gateway URL (in docker-compose, the service name is nanobot-gateway)
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://nanobot-gateway:8081")


@router.post("", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint for processing user messages.
    """
    try:
        # Forward to Gateway for LLM processing
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{GATEWAY_URL}/api/chat",
                json={
                    "message": request.message,
                    "username": request.username,
                    "document_path": request.document_path
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                return ChatResponse(reply=result.get("reply", ""), success=True)
            else:
                raise HTTPException(status_code=response.status_code, detail=f"Gateway error: {response.text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"無法連線至 AI 引擎：{str(e)}")
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
                    # Forward to Gateway's streaming endpoint
                    async with client.stream(
                        "POST", 
                        f"{GATEWAY_URL}/api/stream", 
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
