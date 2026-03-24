"""
WebAPI Channel - HTTP REST API for Nanobot

This channel exposes Nanobot as a REST API for web frontends.
Perfect for custom web UIs, mobile apps, or any HTTP client.

Endpoints:
  POST /api/chat - Send a message and get a response
  GET  /api/health - Health check
  GET  /api/status - Agent status

Usage:
  Enable in config.json:
  {
    "channels": {
      "webapi": {
        "enabled": true,
        "host": "0.0.0.0",
        "port": 8081
      }
    }
  }
"""

import asyncio
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
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


class WebAPIChannel(BaseChannel):
    """
    WebAPI Channel - Exposes Nanobot via HTTP REST API.
    
    This channel creates a lightweight FastAPI server that:
    1. Receives messages from web frontends
    2. Forwards them to the Nanobot message bus
    3. Waits for agent response
    4. Returns the response to the client
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
        self._response_cache: dict[str, asyncio.Future] = {}

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
            """Health check endpoint."""
            return HealthResponse(
                status="online",
                channel=self.name,
            )

        @self.app.post("/api/chat", response_model=ChatResponse)
        async def chat_endpoint(request: ChatRequest):
            """
            Main chat endpoint.
            
            Receives a message, forwards to Nanobot agent, and returns the response.
            """
            from datetime import datetime
            
            # Generate unique message ID for tracking (stored in metadata)
            tracking_id = str(uuid.uuid4())
            
            # Create inbound message with EXACT parameters from events.py
            inbound = InboundMessage(
                channel=self.name,
                sender_id=request.user_id,
                chat_id=request.chat_id,
                content=request.message,
                timestamp=datetime.now(),
                metadata={
                    **(request.metadata or {}),
                    "tracking_id": tracking_id,
                    "username": request.username
                },
            )
            
            # Create a Future to wait for response
            response_future = asyncio.Future()
            self._response_cache[tracking_id] = response_future
            
            try:
                # Send to message bus
                await self.bus.publish("inbound_message", inbound)
                
                # Wait for response (timeout: 60 seconds)
                try:
                    response_text = await asyncio.wait_for(response_future, timeout=60.0)
                except asyncio.TimeoutError:
                    raise HTTPException(status_code=504, detail="Agent response timeout")
                
                return ChatResponse(
                    reply=response_text,
                    chat_id=request.chat_id,
                    message_id=tracking_id,
                )
                
            finally:
                # Clean up cache
                self._response_cache.pop(tracking_id, None)

    async def start(self) -> None:
        """Start the WebAPI server."""
        self._running = True
        
        # Configure uvicorn server
        config = Config(app=self.app, host=self.host, port=self.port, log_level="info")
        self._server = Server(config=config)
        
        logger.info(f"WebAPI Channel started on http://{self.host}:{self.port}")
        logger.info(f"  POST /api/chat - Send messages")
        logger.info(f"  GET  /api/health - Health check")
        
        # Run server
        await self._server.serve()

    async def stop(self) -> None:
        """Stop the WebAPI server."""
        self._running = False
        if self._server:
            self._server.should_exit = True
            logger.info("WebAPI Channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """
        Handle outbound messages from the agent.
        
        This captures agent responses and fulfills the pending request.
        """
        # Try to extract tracking_id from metadata first
        tracking_id = msg.metadata.get("tracking_id") if hasattr(msg, "metadata") else None
        
        if tracking_id and tracking_id in self._response_cache:
            future = self._response_cache[tracking_id]
            if not future.done():
                future.set_result(msg.content)
                logger.debug(f"WebAPI: Response sent for tracking_id {tracking_id}")
                return
        
        # Fallback: try to match by chat_id (for responses without tracking_id)
        for cached_id, future in list(self._response_cache.items()):
            if not future.done():
                future.set_result(msg.content)
                logger.debug(f"WebAPI: Response sent (fallback match) for {cached_id}")
                return
        
        # Unsolicited message (no pending request)
        logger.debug(f"WebAPI: Outbound message (no pending request): {msg.chat_id}")

    async def send_delta(self, chat_id: str, delta: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Stream partial responses (optional enhancement).
        
        For now, we just accumulate deltas in the response cache.
        Could be enhanced with Server-Sent Events or WebSocket.
        """
        # TODO: Implement streaming response via SSE or WebSocket
        pass

    @property
    def supports_streaming(self) -> bool:
        """This channel can support streaming (future enhancement)."""
        return True
