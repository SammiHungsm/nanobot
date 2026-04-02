"""
Document API Router - Handles all document-related endpoints
"""
import os
import json
import zipfile
import io
import hashlib
from datetime import datetime
from pathlib import Path
from loguru import logger

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse, Response, StreamingResponse, JSONResponse
from app.schemas.document import (
    DocumentListResponse,
    DocumentStatus,
    DocumentUploadResponse,
    ProcessingLogResponse,
    QueueStatusResponse,
)
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api", tags=["documents"])

# Global document service instance
document_service: DocumentService = None


def init_document_service(upload_dir: Path, output_dir: Path):
    """Initialize the document service with directories"""
    global document_service
    document_service = DocumentService(upload_dir, output_dir)
    return document_service


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    """List all available documents"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    try:
        documents = []
        for doc in document_service.documents_db.values():
            documents.append({
                "id": doc["id"],
                "name": doc["filename"],
                "path": doc["path"],
                "size": f"{doc['size'] / 1024 / 1024:.2f} MB",
                "date": doc.get("created_at"),
                "status": doc["status"],
                "uploader": doc.get("uploader", "System"),
                "progress": doc.get("progress", 100.0)
            })
        
        # Sort by date descending
        documents.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        return DocumentListResponse(documents=documents, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{doc_id}", response_model=DocumentStatus)
async def get_document_status(doc_id: str):
    """Get processing status for a specific document"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    return DocumentStatus(
        document_id=doc["id"],
        filename=doc["filename"],
        status=doc["status"],
        progress=doc["progress"],
        error_message=doc.get("error_message"),
        output_path=doc.get("output_path"),
        page_count=doc.get("page_count")
    )


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    username: str = "anonymous",
    replace: bool = False  # 👈 接收前端傳來的 replace 參數
):
    """Upload one or more PDF documents"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    try:
        uploaded_files = []
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
        
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                uploaded_files.append({
                    "name": file.filename, 
                    "error": "Only PDF files are supported", 
                    "is_duplicate": False
                })
                continue
            
            # Check file size
            file_size = 0
            file_chunks = []
            while content := await file.read(8192):
                file_chunks.append(content)
                file_size += len(content)
                if file_size > MAX_FILE_SIZE:
                    uploaded_files.append({
                        "name": file.filename,
                        "error": "File size exceeds 50MB limit",
                        "is_duplicate": False
                    })
                    continue
            
            # Reset file position
            await file.seek(0)
            
            # Check for duplicates
            is_duplicate = False
            existing_doc_id = None
            for doc_id, doc in document_service.documents_db.items():
                if doc["filename"] == file.filename:
                    is_duplicate = True
                    existing_doc_id = doc_id
                    break
            
            # 🚀 如果檔案已存在且前端沒有要求強制覆蓋，回傳 409 Conflict
            if is_duplicate and not replace:
                return JSONResponse(
                    status_code=409, 
                    content={
                        "error": "File already exists", 
                        "code": "FILE_EXISTS",
                        "filename": file.filename,
                        "existing_doc_id": existing_doc_id
                    }
                )
            
            # 如果 replace=True 或是檔案不存在，繼續處理
            if is_duplicate and replace:
                # 刪除舊的文檔記錄
                document_service.delete_document(existing_doc_id)
                logger.info(f"🔄 Replacing existing document: {file.filename} (ID: {existing_doc_id})")
            
            # Save file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
            file_path = document_service.upload_dir / safe_filename
            
            file_hash = hashlib.sha256()
            actual_size = 0
            
            with open(file_path, 'wb') as f:
                for chunk in file_chunks:
                    f.write(chunk)
                    actual_size += len(chunk)
                    file_hash.update(chunk)
            
            # Add to document service
            doc_id = await document_service.add_document(
                filename=file.filename,
                file_path=str(file_path),
                uploader=username,
                file_size=actual_size,
                replace=replace  # 👈 傳遞 replace 參數
            )
            
            uploaded_files.append({
                "id": doc_id,
                "name": file.filename,
                "path": str(file_path),
                "size": f"{actual_size / 1024 / 1024:.2f} MB",
                "status": "queued",
                "progress": 0.0,
                "is_duplicate": False
            })
        
        # Start queue processor if not running
        if not document_service.queue_running:
            document_service.queue_running = True
            background_tasks.add_task(document_service.process_queue)
        
        success_count = len([f for f in uploaded_files if not f.get('is_duplicate')])
        
        return DocumentUploadResponse(
            success=True,
            message=f"Uploaded {success_count} file(s)",
            files=uploaded_files
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    if not document_service.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"success": True, "message": "Document deleted"}


@router.get("/queue/status", response_model=QueueStatusResponse)
async def get_queue_status():
    """Get current queue statistics"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    return document_service.get_queue_status()


@router.get("/logs", response_model=ProcessingLogResponse)
async def get_processing_logs():
    """Get processing logs"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    return ProcessingLogResponse(logs=document_service.processing_logs, success=True)


@router.post("/queue/start")
async def start_queue(background_tasks: BackgroundTasks):
    """Start the processing queue"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    if document_service.queue_running:
        return {"message": "Queue already running"}
    
    document_service.queue_running = True
    background_tasks.add_task(document_service.process_queue)
    return {"message": "Queue started"}


@router.post("/queue/stop")
async def stop_queue():
    """Stop the processing queue"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    document_service.queue_running = False
    return {"message": "Queue will stop after current document"}


@router.get("/pdf/{doc_id}/output")
async def get_processed_output(doc_id: str):
    """Get processed JSON output from OpenDataLoader"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    
    # 🛠️ 嘗試讀取真實的 OpenDataLoader 原始輸出 JSON
    # 路徑必須與 opendataloader_processor.py 中保存的路徑一致
    DATA_DIR = os.getenv("DATA_DIR", "/app/data/raw")
    
    # 可能的 JSON 檔案路徑（取決於 processor 怎麼存）
    json_paths = [
        os.path.join(DATA_DIR, doc_id, "output.json"),
        os.path.join(DATA_DIR, f"{doc_id}.json"),
        doc.get("output_path")  #  fallback 到資料庫記錄的路徑
    ]
    
    for json_path in json_paths:
        if json_path and Path(json_path).exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                
                # 直接回傳真實的 OpenDataLoader 原始數據
                return {
                    "metadata": {
                        "status": "Loaded from Disk",
                        "message": f"Successfully loaded raw OpenDataLoader output for {doc_id}."
                    },
                    "content": raw_data
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error reading JSON output: {str(e)}")
    
    # Fallback: 如果找不到 JSON 檔案，回傳資料庫狀態
    return {
        "metadata": {
            "status": "In PostgreSQL Database",
            "message": f"Document {doc.get('filename')} has been successfully parsed."
        },
        "content": [
            {
                "type": "success",
                "text": "📊 Raw data has been successfully extracted and stored in the PostgreSQL database for Vanna RAG training. You can now start chatting with it!"
            }
        ]
    }


@router.get("/pdf/{doc_id}/output/download")
async def download_processed_output(doc_id: str):
    """Download processed JSON output file"""
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail="Document processing not complete")
    
    output_path = doc.get("output_path")
    
    # If file exists, download it
    if output_path and Path(output_path).exists():
        output_filename = Path(doc["filename"]).stem + "_processed.json"
        return FileResponse(
            str(output_path),
            filename=output_filename,
            media_type="application/json"
        )
    
    # Fallback: Return status JSON
    output_filename = Path(doc["filename"]).stem + "_status.json"
    status_content = {
        "metadata": {
            "document": doc.get("filename"),
            "status": "In PostgreSQL Database",
            "message": "This document has been parsed and stored in PostgreSQL for Vanna RAG training."
        },
        "note": "Raw data is stored in the document_chunks table. Use the Vanna API to query it."
    }
    
    return Response(
        content=json.dumps(status_content, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={output_filename}"}
    )


@router.get("/pdf/{doc_id}/output/download-all")
async def download_all_raw_output(doc_id: str):
    """
    Download all raw output (JSON tables + images) as a ZIP file.
    This endpoint packages all artifacts from the data directory.
    """
    if document_service is None:
        raise HTTPException(status_code=500, detail="Document service not initialized")
    
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail="Document processing not complete")
    
    # Get the data directory from document service
    data_dir = document_service.output_dir / doc_id
    
    if not data_dir.exists():
        raise HTTPException(status_code=404, detail="No raw output found for this document")
    
    # Collect all files in the document directory
    files_to_include = []
    for file_path in data_dir.rglob("*"):
        if file_path.is_file():
            files_to_include.append(file_path)
    
    if not files_to_include:
        raise HTTPException(status_code=404, detail="No files found in raw output directory")
    
    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in files_to_include:
            # Calculate relative path for the ZIP structure
            arcname = file_path.relative_to(data_dir)
            zip_file.write(file_path, arcname=str(arcname))
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={doc['filename']}_raw_output.zip"}
    )
