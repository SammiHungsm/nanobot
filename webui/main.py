"""
Nanobot Web UI - Main Entry Point
Serves the HTML frontend and provides API endpoints
"""
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn
import os
import shutil
from pathlib import Path
from typing import Optional

# Import the core logic
from chat_logic import process_chat_message
from fastapi.responses import StreamingResponse
import aiofiles
import hashlib
from datetime import datetime

# Initialize FastAPI application
app = FastAPI(title="Nanobot Financial Chat", version="1.0.0")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the directory where this script is located
BASE_DIR = Path(__file__).parent

# PDF Upload directory - Use environment variable or default to mounted volume
PDF_UPLOAD_DIR = Path(os.getenv("PDF_UPLOAD_DIR", "/data/pdfs"))
PDF_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Database configuration for tracking uploads
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports")

# Define request/response models
class ChatRequest(BaseModel):
    message: str
    username: str = "anonymous"
    document_path: str = None

class ChatResponse(BaseModel):
    reply: str
    success: bool = True

class DocumentListResponse(BaseModel):
    documents: list
    success: bool = True

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the HTML frontend."""
    html_path = BASE_DIR / "ui.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main endpoint for the web frontend to send chat messages.
    """
    try:
        # Pass the message to the isolated logic function
        reply_text = await process_chat_message(
            request.message,
            request.username,
            request.document_path
        )
        return ChatResponse(reply=reply_text, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents", response_model=DocumentListResponse)
async def list_documents():
    """
    List available PDF documents in the upload directory.
    """
    try:
        documents = []
        
        # Scan upload directory
        if PDF_UPLOAD_DIR.exists():
            for pdf_file in PDF_UPLOAD_DIR.glob("*.pdf"):
                stat = pdf_file.stat()
                documents.append({
                    "id": pdf_file.stem,
                    "name": pdf_file.name,
                    "path": str(pdf_file.absolute()),
                    "size": f"{stat.st_size / 1024 / 1024:.2f} MB",
                    "date": stat.st_mtime,
                    "status": "Ready",
                    "uploader": "System"
                })
        
        # Sort by date (newest first)
        documents.sort(key=lambda x: x['date'], reverse=True)
        
        return DocumentListResponse(documents=documents, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), username: str = "anonymous"):
    """
    Handle PDF document upload with progress tracking.
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
        file_path = PDF_UPLOAD_DIR / safe_filename
        
        # Calculate file hash for deduplication
        file_hash = hashlib.sha256()
        file_size = 0
        
        # Save file and calculate hash simultaneously
        async with aiofiles.open(file_path, 'wb') as out_file:
            while content := await file.read(8192):
                await out_file.write(content)
                file_hash.update(content)
                file_size += len(content)
        
        file_hash_hex = file_hash.hexdigest()
        
        # Generate doc_id
        doc_hash = hashlib.md5(safe_filename.encode()).hexdigest()[:8]
        doc_id = f"{Path(file.filename).stem}_{doc_hash}"
        
        # Queue for processing by ingestion worker
        background_tasks.add_task(
            queue_document_for_processing,
            str(file_path),
            doc_id,
            username
        )
        
        return {
            "success": True,
            "message": f"File uploaded successfully: {file.filename}",
            "file": {
                "id": doc_id,
                "name": file.filename,
                "path": str(file_path),
                "size": f"{file_size / 1024 / 1024:.2f} MB",
                "hash": file_hash_hex[:16] + "...",
                "status": "processing"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


async def queue_document_for_processing(file_path: str, doc_id: str, username: str):
    """
    Queue uploaded document for processing by the ingestion worker.
    This runs in the background.
    """
    try:
        # In a real implementation, this would:
        # 1. Insert into documents table with status='pending'
        # 2. Add to processing_queue table
        # 3. Notify ingestion worker via signal or poll
        
        # For now, just log it
        print(f"📥 Document queued for processing: {doc_id} ({file_path})")
        
        # TODO: Call OpenDataLoader processor directly or via queue
        # from nanobot.ingestion import OpenDataLoaderProcessor
        # processor = OpenDataLoaderProcessor(DB_URL, str(PDF_UPLOAD_DIR))
        # await processor.connect()
        # await processor.process_pdf(file_path, company_id=1, doc_id=doc_id)
        # await processor.close()
        
    except Exception as e:
        print(f"❌ Error processing document {doc_id}: {e}")

@app.get("/health")
async def health_check():
    """Simple endpoint to verify the server is running."""
    return {
        "status": "online",
        "service": "nanobot-webui",
        "mcp_connection": "ready",
        "version": "1.0.0"
    }
    
@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Streaming endpoint for the web frontend to receive typewriter effect.
    """
    # 注意：我哋唔再 return JSON，而係 return 一個 Generator (生成器)
    from chat_logic import process_chat_message_stream
    
    return StreamingResponse(
        process_chat_message_stream(request.message, request.username, request.document_path),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    # Run the server
    print("=" * 60)
    print("🚀 Starting Nanobot Web UI Server...")
    print("=" * 60)
    print(f"📂 Base Directory: {BASE_DIR}")
    print(f"🌐 Frontend: http://localhost:3000")
    print(f"🔌 API: http://localhost:8080/api/chat")
    print(f"❤️  Health: http://localhost:8080/health")
    print("=" * 60)
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
