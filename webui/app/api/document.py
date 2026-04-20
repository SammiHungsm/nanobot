"""
Document API Router - Handles all document-related endpoints
🎯 Architecture: True Dependency Injection using FastAPI Depends()
"""
import json
import zipfile
import io
import hashlib
from datetime import datetime
from pathlib import Path
from loguru import logger
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, Depends
from fastapi.responses import FileResponse, Response, StreamingResponse, JSONResponse

from app.core.config import settings
from app.schemas.document import (
    DocumentListResponse,
    DocumentStatus,
    DocumentUploadResponse,
    ProcessingLogResponse,
    QueueStatusResponse,
)
from app.services.document_service import DocumentService


router = APIRouter(prefix="/api", tags=["documents"])


def get_document_service(request: Request) -> DocumentService:
    """
    依赖注入函数：从 app.state 获取 document service
    
    Benefits:
    - 无全局变量
    - 易于单元测试
    - FastAPI 最佳实践
    """
    return request.app.state.document_service


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(document_service: DocumentService = Depends(get_document_service)):
    """List all available documents"""
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
        
        documents.sort(key=lambda x: x.get('date', ''), reverse=True)
        return DocumentListResponse(documents=documents, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{doc_id}", response_model=DocumentStatus)
async def get_document_status(doc_id: str, document_service: DocumentService = Depends(get_document_service)):
    """Get processing status for a specific document"""
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
    document_service: DocumentService = Depends(get_document_service),  # 🌟 真正依赖注入
    files: list[UploadFile] = File(...),
    username: str = Form("anonymous"),
    replace: bool = Form(False), 
    doc_type: str = Form("annual_report"), 
    is_index_report: bool = Form(False),
    index_theme: str = Form(None),
    confirmed_doc_industry: str = Form(None)
):
    """Upload one or more PDF documents with explicit document type declaration"""
    # 🌟 Worker 已由 lifespan 全局管理，无需 BackgroundTasks
    logger.info(f"📥 收到上傳請求: {len(files)} 文件, 類型: {doc_type}")
    
    if is_index_report or doc_type == "index_report":
        logger.info(f"📊 規則 A 啟用: 行業 '{confirmed_doc_industry}'")
    
    try:
        uploaded_files = []
        # 🌟 使用統一配置 (settings.MAX_UPLOAD_SIZE_MB)
        MAX_FILE_SIZE = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                uploaded_files.append({"name": file.filename, "error": "Only PDF files", "is_duplicate": False})
                continue
            
            # 🌟 先生成目标文件路径（用于边读边写）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
            file_path = document_service.upload_dir / safe_filename
            
            actual_size = 0
            file_hash = hashlib.sha256()
            size_exceeded = False
            
            # 🌟 修正：边读取边写入硬盘 (Streaming to Disk)，极大节省内存！
            # 避免多人同时上传时触发 OOM (Out of Memory)
            with open(file_path, 'wb') as f:
                while content := await file.read(8192):
                    f.write(content)
                    actual_size += len(content)
                    file_hash.update(content)
                    
                    if actual_size > MAX_FILE_SIZE:
                        size_exceeded = True
                        break
            
            if size_exceeded:
                # 删除不完整的文件
                file_path.unlink()
                uploaded_files.append({"name": file.filename, "error": f"File size exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit", "is_duplicate": False})
                continue
            
            # Check duplicates (基于 filename，不是基于 doc_id)
            is_duplicate = False
            existing_doc_id = None
            for doc_id, doc in document_service.documents_db.items():
                if doc["filename"] == file.filename:
                    is_duplicate = True
                    existing_doc_id = doc_id
                    break
            
            if is_duplicate and not replace:
                # 删除刚上传的文件（因为不覆盖）
                file_path.unlink()
                return JSONResponse(
                    status_code=409, 
                    content={"error": "File already exists", "code": "FILE_EXISTS", "filename": file.filename, "existing_doc_id": existing_doc_id}
                )
            
            if is_duplicate and replace:
                # 🌟 删除旧文档（使用 await）
                await document_service.delete_document(existing_doc_id)
                logger.info(f"🔄 Replacing: {file.filename} (old ID: {existing_doc_id})")
            
            # Add document to service（此时文件已写入硬盘）
            doc_id = await document_service.add_document(
                filename=file.filename,
                file_path=str(file_path),
                uploader=username,
                file_size=actual_size,
                replace=replace,
                doc_type=doc_type,
                is_index_report=is_index_report,
                index_theme=index_theme,
                confirmed_doc_industry=confirmed_doc_industry
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
        
        # 🌟 Worker 已由 lifespan 全局管理，无需 BackgroundTasks
        # Queue Worker 在 main.py 的 lifespan 中启动，永久运行
        # 文件入队后，Worker 会自动检测并处理
        
        success_count = len([f for f in uploaded_files if not f.get('is_duplicate')])
        return DocumentUploadResponse(success=True, message=f"Uploaded {success_count} file(s)", files=uploaded_files)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, document_service: DocumentService = Depends(get_document_service)):
    """Delete a document"""
    success = await document_service.delete_document(doc_id)  # 🌟 补上 await
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "message": "Document deleted"}


@router.get("/queue/status", response_model=QueueStatusResponse)
async def get_queue_status(document_service: DocumentService = Depends(get_document_service)):
    """Get current queue statistics"""
    return document_service.get_queue_status()


@router.get("/logs", response_model=ProcessingLogResponse)
async def get_processing_logs(document_service: DocumentService = Depends(get_document_service)):
    """Get processing logs"""
    return ProcessingLogResponse(logs=document_service.processing_logs, success=True)


@router.post("/queue/start")
async def start_queue(document_service: DocumentService = Depends(get_document_service)):
    """Start the processing queue (Worker 已由 lifespan 管理)"""
    if document_service.queue_running:
        return {"message": "Queue already running (lifespan-managed)", "status": "active"}
    document_service.queue_running = True
    return {"message": "Queue flag set to True (Worker managed by lifespan)", "status": "active"}


@router.post("/queue/stop")
async def stop_queue(document_service: DocumentService = Depends(get_document_service)):
    """Stop the processing queue"""
    document_service.queue_running = False
    return {"message": "Queue will stop after current document"}


@router.post("/documents/{doc_id}/retry")
async def retry_document(doc_id: str, document_service: DocumentService = Depends(get_document_service)):
    """Retry failed document"""
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    if doc["status"] not in ["failed", "Failed"]:
        raise HTTPException(status_code=400, detail=f"Cannot retry: {doc['status']}")
    
    doc["status"] = "queued"
    doc["progress"] = 0.0
    doc["error_message"] = None
    
    # 🌟 Worker 已由 lifespan 全局管理，文件入队后自动处理
    logger.info(f"🔄 Retrying: {doc['filename']}")
    return {"success": True, "message": f"Document {doc['filename']} queued for retry (Worker: lifespan-managed)"}


@router.post("/documents/batch-delete")
async def batch_delete_documents(doc_ids: list[str], document_service: DocumentService = Depends(get_document_service)):
    """Batch delete documents"""
    deleted_count = 0
    failed_count = 0
    
    for doc_id in doc_ids:
        if await document_service.delete_document(doc_id):  # 🌟 补上 await
            deleted_count += 1
        else:
            failed_count += 1
    
    return {"success": True, "deleted_count": deleted_count, "failed_count": failed_count, "message": f"Deleted {deleted_count} document(s)"}


@router.get("/documents/batch-download")
async def batch_download_documents(doc_ids: str, document_service: DocumentService = Depends(get_document_service)):
    """Batch download documents as ZIP"""
    doc_id_list = doc_ids.split(",")
    files_to_zip = []
    
    for doc_id in doc_id_list:
        if doc_id in document_service.documents_db:
            doc = document_service.documents_db[doc_id]
            file_path = Path(doc["path"])
            if file_path.exists():
                files_to_zip.append((file_path, doc["filename"]))
    
    if not files_to_zip:
        raise HTTPException(status_code=404, detail="No documents found")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path, filename in files_to_zip:
            zip_file.write(file_path, arcname=filename)
    
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=documents_batch.zip"})


@router.get("/pdf/{doc_id}/preview")
async def preview_pdf(doc_id: str, document_service: DocumentService = Depends(get_document_service)):
    """Preview a PDF document in browser"""
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    file_path = Path(doc["path"])
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(str(file_path), media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={doc['filename']}"})


@router.get("/pdf/{doc_id}/download")
async def download_pdf(doc_id: str, document_service: DocumentService = Depends(get_document_service)):
    """Download a PDF document"""
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    file_path = Path(doc["path"])
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(str(file_path), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={doc['filename']}"})


@router.get("/pdf/{doc_id}/output")
async def get_processed_output(doc_id: str, document_service: DocumentService = Depends(get_document_service)):
    """Get processed JSON output"""
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    
    # 🌟 使用統一配置
    json_paths = [
        Path(settings.DATA_DIR) / doc_id / "output.json",
        Path(settings.DATA_DIR) / f"{doc_id}.json",
        doc.get("output_path")
    ]
    
    for json_path in json_paths:
        if json_path and Path(json_path).exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                return {"metadata": {"status": "Loaded from Disk"}, "content": raw_data}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error reading JSON: {str(e)}")
    
    return {
        "metadata": {"status": "In PostgreSQL Database", "message": f"Document {doc.get('filename')} parsed successfully."},
        "content": [{"type": "success", "text": "📊 Data stored in PostgreSQL for Vanna RAG training."}]
    }


@router.get("/pdf/{doc_id}/output/download")
async def download_processed_output(doc_id: str, document_service: DocumentService = Depends(get_document_service)):
    """Download processed JSON output"""
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail="Document processing not complete")
    
    output_path = doc.get("output_path")
    
    if output_path and Path(output_path).exists():
        output_filename = Path(doc["filename"]).stem + "_processed.json"
        return FileResponse(str(output_path), filename=output_filename, media_type="application/json")
    
    output_filename = Path(doc["filename"]).stem + "_status.json"
    status_content = {
        "metadata": {"document": doc.get("filename"), "status": "In PostgreSQL"},
        "note": "Raw data stored in document_chunks. Use Vanna API to query."
    }
    
    return Response(
        content=json.dumps(status_content, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={output_filename}"}
    )


@router.get("/pdf/{doc_id}/output/download-all")
async def download_all_raw_output(doc_id: str, document_service: DocumentService = Depends(get_document_service)):
    """Download all raw output as ZIP"""
    if doc_id not in document_service.documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc = document_service.documents_db[doc_id]
    
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail="Document processing not complete")
    
    data_dir = document_service.output_dir / doc_id
    
    if not data_dir.exists():
        raise HTTPException(status_code=404, detail="No raw output found")
    
    files_to_include = [f for f in data_dir.rglob("*") if f.is_file()]
    
    if not files_to_include:
        raise HTTPException(status_code=404, detail="No files in output directory")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in files_to_include:
            arcname = file_path.relative_to(data_dir)
            zip_file.write(file_path, arcname=str(arcname))
    
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={doc['filename']}_raw_output.zip"})