"""
Document Service - Handles document management and processing queue

🌟 重構後使用 DocumentPipeline (統一入口)
- OpenDataLoaderProcessor 已廢棄
- 使用 DocumentPipeline.process_pdf_full 作為唯一入口
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from loguru import logger

# 🌟 使用 DocumentPipeline (統一入口)
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
        
        # 🌟 初始化 DocumentPipeline (統一入口)
        db_url = os.getenv(
            "DATABASE_URL", 
            "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/annual_reports"
        )
        data_dir = os.getenv("DATA_DIR", "/app/data/raw")
        self.pipeline = DocumentPipeline(db_url=db_url, data_dir=data_dir, use_opendataloader=True)
        
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
        # Keep only last 100 logs
        if len(self.processing_logs) > 100:
            self.processing_logs.pop(0)
        logger.info(f"[{timestamp}] [{log_type.upper()}] {message}")
    
    async def add_document(
        self,
        filename: str,
        file_path: str,
        uploader: str = "System",
        file_size: int = 0,
        replace: bool = False,  # 👈 新增 replace 參數
        doc_type: str = "annual_report"  # 🎯 顯式宣告文件類型
    ) -> str:
        """
        Add a document to the database and queue for processing.
        
        Args:
            filename: 檔案名稱
            file_path: 檔案路徑
            uploader: 上傳者
            file_size: 檔案大小
            replace: 是否強制重新處理 (覆蓋已存在的文檔)
            doc_type: 文件類型 ('annual_report' 或 'index_report')
            
        Returns:
            document_id: Unique identifier for the document
        """
        # Generate document ID
        doc_hash = hashlib.md5(filename.encode()).hexdigest()[:8]
        doc_id = f"{Path(filename).stem}_{doc_hash}"
        
        # 🎯 根據文件類型決定處理方式
        type_label = "恆指報表" if doc_type == "index_report" else "年報"
        logger.info(f"📥 新增文檔: {filename} (類型: {type_label})")
        
        # Add to database
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
            "replace": replace,  # 👈 存儲 replace 標記
            "doc_type": doc_type,  # 🎯 存儲顯式文件類型
        }
        
        # Add to processing queue
        await self.processing_queue.put(doc_id)
        self.add_processing_log(f"📥 佇列新增: {filename} ({type_label})", "info")
        
        return doc_id
    
    async def process_queue(self):
        """Background task to process the document queue"""
        while True:
            try:
                # Get next document from queue
                doc_id = await asyncio.wait_for(self.processing_queue.get(), timeout=1.0)
                
                if doc_id not in self.documents_db:
                    continue
                
                doc = self.documents_db[doc_id]
                self.add_processing_log(f"Starting to process: {doc['filename']} (ID: {doc_id})", "info")
                
                # Update status to processing
                doc["status"] = "processing"
                doc["progress"] = 5.0
                
                try:
                    # 🎯 基於顯式宣告的絕對分流 (Update as need)
                    doc_type = doc.get("doc_type", "annual_report")
                    
                    # 💡 定義進度更新回調函數
                    def update_progress(percent: float, message: str):
                        """更新處理進度"""
                        doc["progress"] = percent
                        doc["status_message"] = message
                        self.add_processing_log(f"[{doc['filename']}] {message}", "info")
                    
                    if doc_type == "index_report":
                        # 🎯 路線 A：恆指主數據更新 Pipeline
                        self.add_processing_log(
                            f"🎯 執行路線 A：恆指主數據更新 Pipeline", 
                            "warning"
                        )
                        # TODO: 實現 index_report 處理邏輯
                        # result = await self._process_master_index_report(doc["path"], doc_id)
                        # 暫時使用標準 Pipeline
                        result = await self._process_with_pipeline(doc, update_progress)
                    else:
                        # 📄 路線 B：一般公司年報 Pipeline
                        self.add_processing_log(
                            f"📄 執行路線 B：一般公司年報 Pipeline", 
                            "info"
                        )
                        result = await self._process_with_pipeline(doc, update_progress)
                    
                    # Check if processing failed
                    if result.get("status") == "failed":
                        raise Exception(result.get("error", "Unknown processing error"))
                    
                    # Update progress
                    doc["progress"] = 80.0
                    self.add_processing_log(
                        f"Processing {doc['filename']}: DB insertion & Vanna sync complete", 
                        "info"
                    )
                    
                    # Mark as completed
                    doc["status"] = "completed"
                    doc["progress"] = 100.0
                    doc["page_count"] = result.get("total_chunks", 0)  # Use chunk count as page count
                    doc["result_metadata"] = result
                    
                    self.add_processing_log(f"✅ Processing complete: {doc['filename']}", "success")
                    logger.info(f"✅ Document processed: {doc_id}")
                    
                except Exception as e:
                    doc["status"] = "failed"
                    doc["error_message"] = str(e)
                    doc["progress"] = 0.0
                    self.add_processing_log(f"❌ Processing failed: {doc['filename']} - {str(e)}", "error")
                    logger.error(f"❌ Document processing failed: {doc_id} - {e}")
                
            except asyncio.TimeoutError:
                # No documents in queue
                continue
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
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
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document and its processed output.
        
        Returns:
            True if deleted successfully
        """
        if doc_id not in self.documents_db:
            return False
        
        doc = self.documents_db[doc_id]
        file_path = Path(doc["path"])
        output_path = doc.get("output_path")
        
        # Delete files
        try:
            if file_path.exists():
                file_path.unlink()
            
            if output_path and Path(output_path).exists():
                Path(output_path).unlink()
        except Exception as e:
            logger.error(f"Error deleting files for {doc_id}: {e}")
        
        # Remove from database
        del self.documents_db[doc_id]
        self.add_processing_log(f"Deleted document: {doc['filename']}", "info")
        
        return True
    
    async def _process_with_pipeline(self, doc: dict, update_progress) -> dict:
        """
        🌟 使用 DocumentPipeline 處理 PDF (統一入口)
        
        OpenDataLoaderProcessor 已廢棄，統一使用 DocumentPipeline.process_pdf_full
        
        Args:
            doc: 文檔記錄
            update_progress: 進度更新回調
            
        Returns:
            處理結果
        """
        doc_id = doc["id"]
        
        # 🌟 使用 DocumentPipeline (統一入口)
        await self.pipeline.connect()
        
        try:
            result = await self.pipeline.process_pdf_full(
                pdf_path=doc["path"], 
                company_id=None,  # 由 Vision LLM 從封面自動提取
                doc_id=doc_id,
                progress_callback=update_progress,
                replace=doc.get("replace", False)
            )
            
            return result
        finally:
            await self.pipeline.close()
