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
BASE_DIR = Path(__file__).resolve().parent

# Static files directory
STATIC_DIR = BASE_DIR / "static"

# Debug: Print paths
print(f"BASE_DIR: {BASE_DIR}")
print(f"STATIC_DIR: {STATIC_DIR}")
print(f"index.html exists: {(STATIC_DIR / 'index.html').exists()}")

# PDF Upload directory
PDF_UPLOAD_DIR = Path(os.getenv("PDF_UPLOAD_DIR", "./uploads")).resolve()
PDF_OUTPUT_DIR = Path(os.getenv("PDF_OUTPUT_DIR", "./outputs")).resolve()
PDF_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory document tracking (replace with DB in production)
documents_db = {}
processing_queue = asyncio.Queue()
queue_running = False
processing_logs = []  # Store processing logs

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

class ProcessingLogResponse(BaseModel):
    logs: list
    success: bool = True

def add_processing_log(message: str, log_type: str = "info"):
    """Add a processing log entry"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "message": message,
        "type": log_type,
        "id": f"log_{datetime.now().timestamp()}_{hash(message) % 10000}"
    }
    processing_logs.append(log_entry)
    # Keep only last 100 logs
    if len(processing_logs) > 100:
        processing_logs.pop(0)
    print(f"[{timestamp}] [{log_type.upper()}] {message}")

class DocumentStatusResponse(BaseModel):
    document_id: str
    filename: str
    status: str  # pending, queued, processing, completed, failed
    progress: float
    error_message: str = None
    output_path: str = None
    page_count: int = None

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the HTML frontend."""
    index_path = STATIC_DIR / "index.html"
    print(f"Attempting to serve: {index_path}")
    print(f"File exists: {index_path.exists()}")
    
    if not index_path.exists():
        print(f"ERROR: File not found at {index_path}")
        raise HTTPException(status_code=404, detail=f"Frontend not found at {index_path}")
    
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
            print(f"Serving index.html ({len(content)} bytes)")
            return HTMLResponse(content=content)
    except Exception as e:
        print(f"ERROR reading file: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading frontend: {str(e)}")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
        seen_paths = set()
        
        # Scan upload directory
        if PDF_UPLOAD_DIR.exists():
            for pdf_file in PDF_UPLOAD_DIR.glob("*.pdf"):
                abs_path = str(pdf_file.absolute())
                if abs_path in seen_paths:
                    continue
                seen_paths.add(abs_path)
                
                stat = pdf_file.stat()
                # Try to find tracking info
                doc_info = None
                for doc in documents_db.values():
                    if doc.get("path") == abs_path:
                        doc_info = doc
                        break
                
                documents.append({
                    "id": doc_info["id"] if doc_info else pdf_file.stem,
                    "name": pdf_file.name,
                    "path": abs_path,
                    "size": f"{stat.st_size / 1024 / 1024:.2f} MB",
                    "date": stat.st_mtime,
                    "status": doc_info["status"] if doc_info else "Ready",
                    "uploader": doc_info.get("uploader", "System") if doc_info else "System",
                    "progress": doc_info.get("progress", 100.0) if doc_info else 100.0
                })
        
        # Also include tracked documents (even if file doesn't exist yet)
        for doc in documents_db.values():
            if doc["path"] not in seen_paths:
                documents.append({
                    "id": doc["id"],
                    "name": doc["filename"],
                    "path": doc["path"],
                    "size": f"{doc['size'] / 1024 / 1024:.2f} MB",
                    "date": doc.get("created_at", datetime.now().isoformat()),
                    "status": doc["status"],
                    "uploader": doc.get("uploader", "System"),
                    "progress": doc.get("progress", 0.0)
                })
        
        # Sort by date (newest first)
        documents.sort(key=lambda x: x.get('date', '') if isinstance(x.get('date'), str) else x.get('date', 0), reverse=True)
        
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


@app.get("/api/logs")
async def get_processing_logs():
    """
    Get processing logs.
    """
    return {
        "logs": processing_logs,
        "success": True
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
async def upload_document(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...), username: str = "anonymous"):
    """
    Handle PDF document upload with progress tracking and OpenDataLoader integration.
    Supports multiple file uploads in a single request.
    """
    try:
        uploaded_files = []
        add_processing_log(f"Starting upload of {len(files)} file(s) by {username}", "info")
        
        for file in files:
            # Validate file type
            if not file.filename.lower().endswith('.pdf'):
                add_processing_log(f"Rejected non-PDF file: {file.filename}", "warning")
                uploaded_files.append({
                    "name": file.filename,
                    "error": "Only PDF files are supported",
                    "is_duplicate": False
                })
                continue
            
            # Check for duplicate by filename
            is_duplicate = False
            existing_doc = None
            for doc_id, doc in documents_db.items():
                if doc["filename"] == file.filename and doc["status"] in ["completed", "queued", "processing"]:
                    is_duplicate = True
                    existing_doc = doc
                    add_processing_log(f"Detected duplicate: {file.filename} (ID: {doc_id})", "info")
                    break
            
            if is_duplicate:
                uploaded_files.append({
                    "id": existing_doc["id"],
                    "name": file.filename,
                    "path": existing_doc["path"],
                    "size": f"{existing_doc['size'] / 1024 / 1024:.2f} MB",
                    "status": existing_doc["status"],
                    "progress": existing_doc.get("progress", 0.0),
                    "is_duplicate": True
                })
                continue
            
            add_processing_log(f"Uploading: {file.filename}", "info")
            
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
            add_processing_log(f"Queued for processing: {file.filename} (ID: {doc_id})", "success")
            
            # Start queue processor if not running
            global queue_running
            if not queue_running:
                background_tasks.add_task(process_queue)
                queue_running = True
                add_processing_log("Processing queue started", "info")
            
            uploaded_files.append({
                "id": doc_id,
                "name": file.filename,
                "path": str(file_path),
                "size": f"{file_size / 1024 / 1024:.2f} MB",
                "hash": file_hash_hex[:16] + "...",
                "status": "queued",
                "progress": 0.0,
                "is_duplicate": False
            })
        
        # Start queue if not running
        if not queue_running:
            background_tasks.add_task(process_queue)
            queue_running = True
        
        add_processing_log(f"Upload complete: {len([f for f in uploaded_files if not f.get('is_duplicate')])} file(s) uploaded", "success")
        
        return {
            "success": True,
            "message": f"Uploaded {len([f for f in uploaded_files if not f.get('is_duplicate')])} file(s)",
            "files": uploaded_files
        }
        
    except HTTPException:
        raise
    except Exception as e:
        add_processing_log(f"Upload failed: {str(e)}", "error")
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
            add_processing_log(f"Starting to process: {doc['filename']} (ID: {doc_id})", "info")
            
            # Update status to processing
            doc["status"] = "processing"
            doc["progress"] = 5.0
            
            try:
                # Process with OpenDataLoader
                output_file = PDF_OUTPUT_DIR / f"{Path(doc['filename']).stem}_processed.json"
                
                # Update progress
                doc["progress"] = 20.0
                add_processing_log(f"Processing {doc['filename']}: Converting PDF to JSON (20%)", "info")
                
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
                add_processing_log(f"Processing {doc['filename']}: Extraction complete (80%)", "info")
                
                # Read results
                if output_file.exists():
                    with open(output_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    doc["output_path"] = str(output_file)
                    doc["result_metadata"] = metadata
                    doc["page_count"] = metadata.get("metadata", {}).get("page_count", 0)
                    add_processing_log(f"Processing {doc['filename']}: Output saved ({doc['page_count']} pages)", "success")
                else:
                    add_processing_log(f"Processing {doc['filename']}: Warning - output file not found", "warning")
                
                # Mark as completed
                doc["status"] = "completed"
                doc["progress"] = 100.0
                
                add_processing_log(f"✅ Processing complete: {doc['filename']}", "success")
                print(f"✅ Document processed: {doc_id}")
                
            except Exception as e:
                doc["status"] = "failed"
                doc["error_message"] = str(e)
                doc["progress"] = 0.0
                add_processing_log(f"❌ Processing failed for {doc['filename']}: {str(e)}", "error")
                print(f"❌ Document processing failed: {doc_id} - {e}")
            
            processing_queue.task_done()
            
        except asyncio.TimeoutError:
            # No documents in queue
            await asyncio.sleep(1)
        except Exception as e:
            add_processing_log(f"Queue processing error: {str(e)}", "error")
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
    Serve PDF file for preview in browser (inline display).
    """
    if doc_id not in documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = documents_db[doc_id]
    file_path = Path(doc["path"])
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=doc["filename"],
        headers={"Content-Disposition": "inline"}
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
    print(f"📁 Static Directory: {STATIC_DIR}")
    print(f"📄 Index exists: {(STATIC_DIR / 'index.html').exists()}")
    print(f"🌐 Frontend: http://localhost:8080")
    print(f"🌐 Library: http://localhost:8080/#library")
    print(f"🔌 API: http://localhost:8080/api/chat")
    print(f"❤️  Health: http://localhost:8080/health")
    print("=" * 60)
    print("\n⚠️  NOTE: Server runs on port 8080 (NOT 3000)")
    print("=" * 60)
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
