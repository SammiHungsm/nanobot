"""
WebAPI Channel - HTTP REST API for Nanobot

This channel exposes Nanobot as a REST API for web frontends.
Perfect for custom web UIs, mobile apps, or any HTTP client.

Endpoints:
  POST /api/chat   - Send a message and get full response
  POST /api/stream - Send a message and get streaming response (New!)
  GET  /api/health - Health check
"""

import asyncio
import uuid
import json
import os
from typing import Any, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uvicorn import Config, Server

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.channels.base import BaseChannel


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str
    chat_id: str = "webui-default"
    user_id: str = "webui-user"
    username: str = "Web User"
    metadata: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    reply: str
    chat_id: str
    message_id: str
    success: bool = True


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    channel: str
    version: str = "1.0.0"
    database: str = "unknown"  # Database connectivity status


class WebAPIChannel(BaseChannel):
    """
    WebAPI Channel - Exposes Nanobot via HTTP REST API.
    
    This channel creates a lightweight FastAPI server that:
    1. Receives messages from web frontends
    2. Forwards them to the Nanobot message bus
    3. Handles both synchronous and streaming responses
    """

    name = "webapi"
    display_name = "Web API"

    def __init__(self, config: Any, bus: Any):
        super().__init__(config, bus)
        
        # Configuration
        self.host = config.get("host", "0.0.0.0") if isinstance(config, dict) else getattr(config, "host", "0.0.0.0")
        self.port = config.get("port", 8081) if isinstance(config, dict) else getattr(config, "port", 8081)
        
        # FastAPI app
        self.app = FastAPI(title="Nanobot WebAPI", version="1.0.0")
        self._setup_cors()
        self._setup_routes()
        
        # Server instance
        self._server: Server | None = None
        
        # 🌟 Cache 可以裝 Future (用於同步 /api/chat) 或者 Queue (用於串流 /api/stream)
        self._response_cache: dict[str, Union[asyncio.Future, asyncio.Queue]] = {}

    def _setup_cors(self):
        """Configure CORS for web frontend access."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure this for production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.get("/api/health", response_model=HealthResponse)
        async def health_check():
            """Health check endpoint with database connectivity test."""
            db_status = "unknown"
            try:
                import asyncpg
                db_url = os.getenv("DATABASE_URL", "")
                if db_url:
                    conn = await asyncpg.connect(db_url, timeout=5)
                    await conn.close()
                    db_status = "connected"
                else:
                    db_status = "not_configured"
            except Exception as e:
                db_status = f"error: {str(e)[:50]}"
                
            return HealthResponse(
                status="online",
                channel=self.name,
                database=db_status,
            )

        @self.app.post("/api/chat", response_model=ChatResponse)
        async def chat_endpoint(request: ChatRequest):
            """舊版：同步等待完整回覆 (保留作向下相容)"""
            from datetime import datetime
            tracking_id = str(uuid.uuid4())
            
            inbound = InboundMessage(
                channel=self.name,
                sender_id=request.user_id,
                chat_id=request.chat_id,
                content=request.message,
                timestamp=datetime.now(),
                metadata={
                    **(request.metadata or {}),
                    "tracking_id": tracking_id,
                    "username": request.username,
                    "actual_msg_id": tracking_id
                },
            )
            
            response_future = asyncio.Future()
            self._response_cache[tracking_id] = response_future
            
            try:
                await self.bus.publish_inbound(inbound)
                response_text = await asyncio.wait_for(response_future, timeout=300.0)
                return ChatResponse(
                    reply=response_text,
                    chat_id=request.chat_id,
                    message_id=tracking_id,
                )
            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail="Agent response timeout (300s)")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
            finally:
                asyncio.create_task(self._cleanup_tracking_id(tracking_id))

        @self.app.post("/api/stream")
        async def stream_endpoint(request: ChatRequest):
            """新版：串流打字機效果 (Server-Sent Events)"""
            from datetime import datetime
            tracking_id = str(uuid.uuid4())
            
            # 🌟 使用 Queue 來接收即時字粒
            message_queue = asyncio.Queue()
            self._response_cache[tracking_id] = message_queue
            
            inbound = InboundMessage(
                channel=self.name,
                sender_id=request.user_id,
                chat_id=request.chat_id,
                content=request.message,
                timestamp=datetime.now(),
                metadata={
                    **(request.metadata or {}),
                    "tracking_id": tracking_id,
                    "username": request.username,
                    "actual_msg_id": tracking_id
                },
            )

            async def event_generator():
                try:
                    await self.bus.publish_inbound(inbound)
                    while True:
                        # 等待下一個字粒，超時設為 120 秒 (避免一直卡死)
                        chunk = await asyncio.wait_for(message_queue.get(), timeout=120.0)
                        
                        # Parse the JSON chunk to check for done signal
                        try:
                            chunk_data = json.loads(chunk) if isinstance(chunk, str) else chunk
                            if chunk_data.get("type") == "done":
                                break
                        except (json.JSONDecodeError, TypeError):
                            # Fallback: treat as raw content
                            pass
                        
                        # 🌟 SSE 格式輸出
                        yield f"data: {chunk}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Agent thinking timeout (120s)'})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Stream Error: {str(e)}'})}\n\n"
                finally:
                    await self._cleanup_tracking_id(tracking_id, delay=0)

            return StreamingResponse(event_generator(), media_type="text/event-stream")

    async def start(self) -> None:
        """Start the WebAPI server."""
        self._running = True
        config = Config(app=self.app, host=self.host, port=self.port, log_level="info")
        self._server = Server(config=config)
        logger.info(f"WebAPI Channel started on http://{self.host}:{self.port}")
        logger.info(f"  POST /api/chat   - Send messages (Sync)")
        logger.info(f"  POST /api/stream - Send messages (Streaming)")
        logger.info(f"  GET  /api/health - Health check")
        await self._server.serve()

    async def stop(self) -> None:
        """Stop the WebAPI server."""
        self._running = False
        if self._server:
            self._server.should_exit = True
            logger.info("WebAPI Channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """處理最終完整回覆與進度回報"""
        tracking_id = None
        is_progress = False # 👈 新增：檢查係咪進度回報
        
        if hasattr(msg, "metadata") and msg.metadata:
            tracking_id = msg.metadata.get("tracking_id") or msg.metadata.get("actual_msg_id")
            is_progress = msg.metadata.get("_progress", False) # 👈 新增：讀取進度標籤
        
        if tracking_id and tracking_id in self._response_cache:
            target = self._response_cache[tracking_id]
            
            if isinstance(target, asyncio.Future):
                if not target.done() and not is_progress: 
                    target.set_result(msg.content)
            elif isinstance(target, asyncio.Queue):
                if is_progress:
                    # 🌟 Progress message: use proper JSON SSE format
                    # Frontend will render as italic/progress indicator
                    await target.put(json.dumps({"type": "progress", "content": msg.content}))
                else:
                    # 🌟 如果係最終答案，推入結果並標記 [DONE] 結束
                    await target.put(json.dumps({"type": "content", "content": msg.content}))
                    await target.put(json.dumps({"type": "done"}))
            return

    async def send_delta(self, chat_id: str, delta: str, metadata: dict[str, Any] | None = None) -> None:
        """處理串流字粒"""
        tracking_id = metadata.get("tracking_id") if metadata else None
        
        if tracking_id and tracking_id in self._response_cache:
            target = self._response_cache[tracking_id]
            if isinstance(target, asyncio.Queue):
                # 🌟 將字粒放進 Queue 推俾前端 - use consistent JSON format
                await target.put(json.dumps({"type": "delta", "content": delta}))

    async def _cleanup_tracking_id(self, tracking_id: str, delay: float = 5.0) -> None:
        """Clean up tracking ID from cache after a delay."""
        await asyncio.sleep(delay)
        self._response_cache.pop(tracking_id, None)

    @property
    def supports_streaming(self) -> bool:
        """This channel CAN now support streaming!"""
        return True