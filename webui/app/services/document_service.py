"""
Document Service - Handles document management and processing queue (v3.2)

🌟 v3.2: 使用 DocumentPipeline + LlamaParse
- 移除 OpenDataLoader/Hybrid 配置
- 简化初始化参数
"""
import asyncio
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from loguru import logger

from app.core.config import settings
from nanobot.ingestion.pipeline import DocumentPipeline


class DocumentService:
    """Service for managing documents and processing queue"""
    
    def __init__(self, upload_dir: Path, output_dir: Path):
        self.upload_dir = upload_dir
        self.output_dir = output_dir
        self.documents_db: Dict[str, dict] = {}
        self.processing_queue: asyncio.Queue = asyncio.Queue()
        self.queue_running: bool = False
        self.processing_logs: list = []
        
        # 🌟 延迟初始化 DocumentPipeline
        self._db_url = settings.DATABASE_URL
        self._data_dir = settings.DATA_DIR
        self.pipeline = None
        self._pipeline_connected = False
    
    async def _ensure_pipeline_connected(self):
        """确保 Pipeline 已连接数据库"""
        if not self._pipeline_connected or self.pipeline is None:
            logger.info("🔗 初始化 DocumentPipeline...")
            self.pipeline = DocumentPipeline(
                db_url=self._db_url,
                data_dir=self._data_dir
            )
            await self.pipeline.connect()
            self._pipeline_connected = True
            logger.info("✅ DocumentPipeline 已连接数据库")
    
    def add_processing_log(self, message: str, log_type: str = "info"):
        """Add a processing log entry"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "message": message,
            "type": log_type,
            "id": f"log_{datetime.now().timestamp()}_{hash(message) % 10000}"
        }
        self.processing_logs.append(log_entry)
        if len(self.processing_logs) > 100:
            self.processing_logs.pop(0)
        logger.info(f"[{timestamp}] [{log_type.upper()}] {message}")
    
    async def add_document(
        self,
        filename: str,
        file_path: str,
        uploader: str = "System",
        file_size: int = 0,
        replace: bool = False,
        doc_type: str = "annual_report",
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None
    ) -> str:
        """Add a document to the database and queue for processing."""
        unique_hash = uuid.uuid4().hex[:8]
        safe_stem = Path(filename).stem.replace(" ", "_").replace("-", "_")
        doc_id = f"{safe_stem}_{unique_hash}"
        
        if is_index_report or doc_type == "index_report":
            type_label = f"指数报告 ({confirmed_doc_industry or 'Unknown'})"
        else:
            type_label = "年报"
        
        logger.info(f"📥 新增文档: {filename} (类型: {type_label})")
        
        self.documents_db[doc_id] = {
            "id": doc_id,
            "filename": filename,
            "path": file_path,
            "size": file_size,
            "uploader": uploader,
            "status": "queued",
            "progress": 0.0,
            "error_message": None,
            "created_at": datetime.now().isoformat(),
            "replace": replace,
            "doc_type": doc_type,
            "is_index_report": is_index_report or doc_type == "index_report",
            "index_theme": index_theme,
            "confirmed_doc_industry": confirmed_doc_industry,
        }
        
        await self.processing_queue.put(doc_id)
        self.add_processing_log(f"📥 队列新增: {filename} ({type_label})", "info")
        
        return doc_id
    
    async def process_queue(self):
        """Background task to process the document queue"""
        while True:
            try:
                doc_id = await asyncio.wait_for(self.processing_queue.get(), timeout=1.0)
                
                if doc_id not in self.documents_db:
                    continue
                
                doc = self.documents_db[doc_id]
                self.add_processing_log(f"Starting to process: {doc['filename']} (ID: {doc_id})", "info")
                
                doc["status"] = "processing"
                doc["progress"] = 5.0
                
                try:
                    def update_progress(percent: float, message: str):
                        doc["progress"] = percent
                        doc["status_message"] = message
                        self.add_processing_log(f"[{doc['filename']}] {message}", "info")
                    
                    result = await self._process_with_pipeline(doc, update_progress)
                    
                    if result.get("status") == "failed":
                        raise Exception(result.get("error", "Unknown processing error"))
                    
                    doc["progress"] = 100.0
                    doc["status"] = "completed"
                    doc["page_count"] = result.get("total_chunks", 0)
                    doc["result_metadata"] = result
                    
                    self.add_processing_log(f"✅ Processing complete: {doc['filename']}", "success")
                    
                except Exception as e:
                    import traceback
                    doc["status"] = "failed"
                    doc["error_message"] = str(e)
                    doc["traceback"] = traceback.format_exc()
                    doc["progress"] = 0.0
                    self.add_processing_log(f"❌ Processing failed: {doc['filename']} - {str(e)}", "error")
                    logger.error(f"❌ Document processing failed: {doc_id} - {e}", exc_info=True)
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.warning("Processing queue cancelled")
                break
            except Exception as e:
                logger.error(f"Queue processing error: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    def get_queue_status(self) -> dict:
        """Get current queue statistics"""
        total = len(self.documents_db)
        pending = sum(1 for d in self.documents_db.values() if d["status"] == "pending")
        queued = sum(1 for d in self.documents_db.values() if d["status"] == "queued")
        processing = sum(1 for d in self.documents_db.values() if d["status"] == "processing")
        completed = sum(1 for d in self.documents_db.values() if d["status"] == "completed")
        failed = sum(1 for d in self.documents_db.values() if d["status"] == "failed")
        
        return {
            "total_documents": total,
            "pending_count": pending,
            "queued_count": queued,
            "processing_count": processing,
            "completed_count": completed,
            "failed_count": failed,
            "queue_size": self.processing_queue.qsize(),
            "is_running": self.queue_running
        }
    
    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document and its processed output."""
        if doc_id not in self.documents_db:
            return False
        
        doc = self.documents_db[doc_id]
        file_path = Path(doc["path"])
        
        try:
            if file_path.exists():
                file_path.unlink()
            
            doc_output_dir = self.output_dir / doc_id
            if doc_output_dir.exists():
                import shutil
                shutil.rmtree(doc_output_dir)
        except Exception as e:
            logger.error(f"Error deleting files for {doc_id}: {e}")
        
        try:
            await self._ensure_pipeline_connected()
            if self.pipeline and self.pipeline.db:
                await self.pipeline.db.delete_document(doc_id)
                self.add_processing_log(f"🧹 已从数据库清除: {doc_id}", "info")
        except Exception as e:
            logger.error(f"清除数据库数据失败 {doc_id}: {e}")
        
        del self.documents_db[doc_id]
        self.add_processing_log(f"🗑️ Deleted document: {doc['filename']}", "info")
        
        return True
    
    async def _process_with_pipeline(self, doc: dict, update_progress) -> dict:
        """使用 DocumentPipeline 处理 PDF"""
        doc_id = doc["id"]
        
        await self._ensure_pipeline_connected()
        
        try:
            result = await self.pipeline.process_pdf_full(
                pdf_path=doc["path"],
                company_id=None,
                doc_id=doc_id,
                original_filename=doc["filename"],  # 🌟 v3.3: 传递原始上传文件名
                progress_callback=update_progress,
                replace=doc.get("replace", False),
                is_index_report=doc.get("is_index_report", False),
                index_theme=doc.get("index_theme"),
                confirmed_doc_industry=doc.get("confirmed_doc_industry")
            )
            
            return result
        except Exception as e:
            logger.error(f"Pipeline 处理失败: {e}", exc_info=True)
            raise