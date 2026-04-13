"""
Document Service - Handles document management and processing queue

🌟 重構後使用 DocumentPipeline (統一入口)
- OpenDataLoaderProcessor 已廢棄
- 使用 DocumentPipeline.process_pdf_full 作為唯一入口
- 🎯 Architecture: Uses unified config from core.config
- 🌟 UUID-based doc_id (防止碰撞)
"""
import asyncio
import hashlib
import json
import uuid  # 🌟 新增 UUID 支持
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from loguru import logger

# 🌟 使用统一配置
from app.core.config import settings

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
        
        # 🌟 延迟初始化 DocumentPipeline (避免在 __init__ 中连接数据库)
        self._db_url = settings.DATABASE_URL
        self._data_dir = settings.DATA_DIR
        self.pipeline = None  # 将在首次使用时初始化
        self._pipeline_connected = False
    
    async def _ensure_pipeline_connected(self):
        """确保 Pipeline 已连接数据库"""
        if not self._pipeline_connected or self.pipeline is None:
            logger.info("🔗 初始化 DocumentPipeline 连接...")
            self.pipeline = DocumentPipeline(
                db_url=self._db_url, 
                data_dir=self._data_dir, 
                use_opendataloader=True,
                enable_hybrid=True  # 🌟 启用 Hybrid AI 视觉模式（提取图片）
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
        replace: bool = False,  # 是否強制重新處理 (覆蓋已存在的文檔)
        doc_type: str = "annual_report",  # 文件類型
        # 🌟 新增：指數報告專用參數
        is_index_report: bool = False,
        index_theme: str = None,
        confirmed_doc_industry: str = None
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
            is_index_report: 是否為指數報告
            index_theme: 指數主題 (如 "Hang Seng Biotech Index")
            confirmed_doc_industry: 報告定義的行業 (如 "Biotech")
                - 規則 A: 所有成分股都會被強制指派此行業
            
        Returns:
            document_id: Unique identifier for the document
        """
        # 🌟 修正：使用 UUID 確保即使檔名相同，ID 也絕對唯一
        # 防止不同用戶上傳同名文件時發生碰撞 (Collision Bug)
        unique_hash = uuid.uuid4().hex[:8]
        safe_stem = Path(filename).stem.replace(" ", "_").replace("-", "_")
        doc_id = f"{safe_stem}_{unique_hash}"
        
        # 🌟 根據文件類型決定處理方式
        if is_index_report or doc_type == "index_report":
            type_label = f"指數報告 ({confirmed_doc_industry or 'Unknown'})"
            logger.info(f"📊 規則 A 啟用: 所有成分股將被指派行業 '{confirmed_doc_industry}'")
        else:
            type_label = "年報 (規則 B: AI 提取行業)"
        
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
            "replace": replace,
            "doc_type": doc_type,
            # 🌟 新增指數報告字段
            "is_index_report": is_index_report or doc_type == "index_report",
            "index_theme": index_theme,
            "confirmed_doc_industry": confirmed_doc_industry,
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
                    import traceback
                    doc["status"] = "failed"
                    doc["error_message"] = str(e)
                    doc["traceback"] = traceback.format_exc()
                    doc["progress"] = 0.0
                    self.add_processing_log(f"❌ Processing failed: {doc['filename']} - {str(e)}", "error")
                    logger.error(f"❌ Document processing failed: {doc_id} - {e}", exc_info=True)
                
            except asyncio.TimeoutError:
                # No documents in queue
                continue
            except asyncio.CancelledError:
                # 队列被取消
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
        """
        Delete a document and its processed output.
        🌟 改為 async，並徹底清除 PostgreSQL/ChromaDB 中的幽靈數據
        
        防止 AI 幻覺：
        - 删除文件实体
        - 删除内存记录
        - 🌟 删除数据库中的关联数据
        
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
                
            # 🌟 删除输出目录（如果存在）
            doc_output_dir = self.output_dir / doc_id
            if doc_output_dir.exists():
                import shutil
                shutil.rmtree(doc_output_dir)
                logger.info(f"Deleted output directory: {doc_output_dir}")
        except Exception as e:
            logger.error(f"Error deleting files for {doc_id}: {e}")
        
        # 🌟 從資料庫與向量庫中徹底抹除數據（防止 AI 幻覺）
        try:
            await self._ensure_pipeline_connected()
            if self.pipeline and self.pipeline.db:
                # 🌟 調用 pipeline.db.delete_document() 徹底清除資料庫
                await self.pipeline.db.delete_document(doc_id)
                logger.info(f"✅ 已從資料庫徹底清除: {doc_id}")
                self.add_processing_log(f"🧹 已從資料庫徹底清除: {doc_id}", "info")
        except Exception as e:
            logger.error(f"清除資料庫數據失敗 {doc_id}: {e}")
            self.add_processing_log(f"⚠️ 清除資料庫數據失敗: {doc_id} - {e}", "error")
        
        # Remove from memory database
        del self.documents_db[doc_id]
        self.add_processing_log(f"🗑️ Deleted document: {doc['filename']} (ID: {doc_id})", "info")
        
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
        
        # 🌟 确保 Pipeline 已连接数据库
        await self._ensure_pipeline_connected()
        
        try:
            result = await self.pipeline.process_pdf_full(
                pdf_path=doc["path"], 
                company_id=None,  # 由 Vision LLM 從封面自動提取
                doc_id=doc_id,
                progress_callback=update_progress,
                replace=doc.get("replace", False),
                # 🌟 必須將新參數傳遞畀底層 Pipeline，否則 AI 唔知呢份係指數報告！
                is_index_report=doc.get("is_index_report", False),
                index_theme=doc.get("index_theme"),
                confirmed_doc_industry=doc.get("confirmed_doc_industry")
            )
            
            return result
        except Exception as e:
            logger.error(f"Pipeline 处理失败: {e}", exc_info=True)
            raise
