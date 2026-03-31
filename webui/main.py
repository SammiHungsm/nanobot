"""
Nanobot Web UI - Main Entry Point
Serves the HTML frontend and provides API endpoints with OpenDataLoader integration
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
import asyncio
from datetime import datetime
import hashlib
import json

# Import the core logic
from chat_logic import process_chat_message
from fastapi.responses import StreamingResponse
import aiofiles

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

# PDF Upload directory
PDF_UPLOAD_DIR = Path(os.getenv("PDF_UPLOAD_DIR", "./uploads"))
PDF_OUTPUT_DIR = Path(os.getenv("PDF_OUTPUT_DIR", "./outputs"))
PDF_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory document tracking (replace with DB in production)
documents_db = {}
processing_queue = asyncio.Queue()
queue_running = False

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

class DocumentStatusResponse(BaseModel):
    document_id: str
    filename: str
    status: str  # pending, queued, processing, completed, failed
    progress: float
    error_message: str = None

class DocumentStatusResponse(BaseModel):
    document_id: str
    filename: str
    status: str  # pending, queued, processing, completed, failed
    progress: float
    error_message: str = None

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
                # Try to find tracking info
                doc_info = None
                for doc in documents_db.values():
                    if doc.get("path") == str(pdf_file.absolute()):
                        doc_info = doc
                        break
                
                documents.append({
                    "id": doc_info["id"] if doc_info else pdf_file.stem,
                    "name": pdf_file.name,
                    "path": str(pdf_file.absolute()),
                    "size": f"{stat.st_size / 1024 / 1024:.2f} MB",
                    "date": stat.st_mtime,
                    "status": doc_info["status"] if doc_info else "Ready",
                    "uploader": doc_info.get("uploader", "System"),
                    "progress": doc_info.get("progress", 100.0) if doc_info else 100.0
                })
        
        # Also include tracked documents that haven't been saved yet
        for doc in documents_db.values():
            if not any(d["name"] == doc["filename"] for d in documents):
                documents.append({
                    "id": doc["id"],
                    "name": doc["filename"],
                    "path": doc["path"],
                    "size": f"{doc['size'] / 1024 / 1024:.2f} MB",
                    "date": doc["created_at"],
                    "status": doc["status"],
                    "uploader": doc.get("uploader", "System"),
                    "progress": doc.get("progress", 0.0)
                })
        
        # Sort by date (newest first)
        documents.sort(key=lambda x: x.get('date', '') if isinstance(x.get('date'), str) else x['date'], reverse=True)
        
        return DocumentListResponse(documents=documents, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status/{doc_id}")
async def get_document_status(doc_id: str):
    """
    Get real-time processing status for a document.
    """
    if doc_id not in documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = documents_db[doc_id]
    return {
        "document_id": doc["id"],
        "filename": doc["filename"],
        "status": doc["status"],
        "progress": doc["progress"],
        "error_message": doc.get("error_message"),
        "output_path": doc.get("output_path"),
        "page_count": doc.get("page_count")
    }


@app.get("/api/queue/status")
async def get_queue_status():
    """
    Get current queue statistics.
    """
    total = len(documents_db)
    pending = sum(1 for d in documents_db.values() if d["status"] == "pending")
    queued = sum(1 for d in documents_db.values() if d["status"] == "queued")
    processing = sum(1 for d in documents_db.values() if d["status"] == "processing")
    completed = sum(1 for d in documents_db.values() if d["status"] == "completed")
    failed = sum(1 for d in documents_db.values() if d["status"] == "failed")
    
    return {
        "total_documents": total,
        "pending_count": pending,
        "queued_count": queued,
        "processing_count": processing,
        "completed_count": completed,
        "failed_count": failed,
        "queue_size": processing_queue.qsize(),
        "is_running": queue_running
    }


@app.post("/api/queue/start")
async def start_queue(background_tasks: BackgroundTasks):
    """
    Start the processing queue.
    """
    global queue_running
    if queue_running:
        return {"message": "Queue already running"}
    
    queue_running = True
    background_tasks.add_task(process_queue)
    return {"message": "Queue started"}


@app.post("/api/queue/stop")
async def stop_queue():
    """
    Stop the processing queue.
    """
    global queue_running
    queue_running = False
    return {"message": "Queue will stop after current document"}

@app.post("/api/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), username: str = "anonymous"):
    """
    Handle PDF document upload with progress tracking and OpenDataLoader integration.
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
        file_path = PDF_UPLOAD_DIR / safe_filename
        
        # Calculate file hash and size
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
        
        # Initialize document tracking
        documents_db[doc_id] = {
            "id": doc_id,
            "filename": file.filename,
            "path": str(file_path),
            "size": file_size,
            "uploader": username,
            "status": "queued",
            "progress": 0.0,
            "error_message": None,
            "created_at": datetime.now().isoformat(),
            "hash": file_hash_hex
        }
        
        # Add to processing queue
        await processing_queue.put(doc_id)
        
        # Start queue processor if not running
        global queue_running
        if not queue_running:
            background_tasks.add_task(process_queue)
            queue_running = True
        
        return {
            "success": True,
            "message": f"File uploaded successfully: {file.filename}",
            "file": {
                "id": doc_id,
                "name": file.filename,
                "path": str(file_path),
                "size": f"{file_size / 1024 / 1024:.2f} MB",
                "hash": file_hash_hex[:16] + "...",
                "status": "queued",
                "progress": 0.0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


async def process_queue():
    """
    Background task to process the document queue with OpenDataLoader.
    """
    global queue_running
    
    while True:
        try:
            # Get next document from queue
            doc_id = await asyncio.wait_for(processing_queue.get(), timeout=1.0)
            
            if doc_id not in documents_db:
                continue
            
            doc = documents_db[doc_id]
            
            # Update status to processing
            doc["status"] = "processing"
            doc["progress"] = 5.0
            
            try:
                # Process with OpenDataLoader
                output_file = PDF_OUTPUT_DIR / f"{Path(doc['filename']).stem}_processed.json"
                
                # Update progress
                doc["progress"] = 20.0
                
                # Run OpenDataLoader conversion (in thread pool to avoid blocking)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    run_opendataloader,
                    doc["path"],
                    str(output_file)
                )
                
                # Update progress
                doc["progress"] = 80.0
                
                # Read results
                if output_file.exists():
                    with open(output_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    doc["output_path"] = str(output_file)
                    doc["result_metadata"] = metadata
                    doc["page_count"] = metadata.get("metadata", {}).get("page_count", 0)
                
                # Mark as completed
                doc["status"] = "completed"
                doc["progress"] = 100.0
                
                print(f"✅ Document processed: {doc_id}")
                
            except Exception as e:
                doc["status"] = "failed"
                doc["error_message"] = str(e)
                doc["progress"] = 0.0
                print(f"❌ Document processing failed: {doc_id} - {e}")
            
            processing_queue.task_done()
            
        except asyncio.TimeoutError:
            # No documents in queue
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Queue processing error: {e}")
            await asyncio.sleep(5)


def run_opendataloader(input_path: str, output_path: str):
    """
    Run OpenDataLoader PDF conversion.
    """
    try:
        from opendataloader_pdf import convert
        convert(
            pdf_path=input_path,
            output_path=output_path,
            output_format="json",
            pages="all"
        )
    except ImportError:
        # Fallback: create a mock result if opendataloader not installed
        mock_result = {
            "metadata": {"page_count": 0, "filename": Path(input_path).name},
            "content": []
        }
        with open(output_path, 'w') as f:
            json.dump(mock_result, f)

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
    from chat_logic import process_chat_message_stream
    
    return StreamingResponse(
        process_chat_message_stream(request.message, request.username, request.document_path),
        media_type="text/event-stream"
    )


@app.get("/api/pdf/{doc_id}/preview")
async def preview_pdf(doc_id: str):
    """
    Serve PDF file for preview in browser.
    """
    if doc_id not in documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = documents_db[doc_id]
    file_path = Path(doc["path"])
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    
    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=doc["filename"]
    )


@app.get("/api/pdf/{doc_id}/download")
async def download_pdf(doc_id: str):
    """
    Download original PDF file.
    """
    if doc_id not in documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = documents_db[doc_id]
    file_path = Path(doc["path"])
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    
    return FileResponse(
        str(file_path),
        filename=doc["filename"],
        media_type="application/pdf"
    )


@app.get("/api/pdf/{doc_id}/output")
async def get_processed_output(doc_id: str):
    """
    Get processed JSON output from OpenDataLoader.
    """
    if doc_id not in documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = documents_db[doc_id]
    
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail="Document processing not complete")
    
    output_path = doc.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Processed output not found")
    
    with open(output_path, 'r', encoding='utf-8') as f:
        result = json.load(f)
    
    return result


@app.get("/api/pdf/{doc_id}/output/download")
async def download_processed_output(doc_id: str):
    """
    Download processed JSON output file.
    """
    if doc_id not in documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = documents_db[doc_id]
    
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail="Document processing not complete")
    
    output_path = doc.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Processed output not found")
    
    output_filename = Path(doc["filename"]).stem + "_processed.json"
    
    return FileResponse(
        str(output_path),
        filename=output_filename,
        media_type="application/json"
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
