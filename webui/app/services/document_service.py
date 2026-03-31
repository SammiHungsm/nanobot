"""
Document Service - Handles document management and processing queue
"""
import asyncio
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from loguru import logger

from app.services.pdf_service import process_pdf_async


class DocumentService:
    """Service for managing documents and processing queue"""
    
    def __init__(self, upload_dir: Path, output_dir: Path):
        self.upload_dir = upload_dir
        self.output_dir = output_dir
        self.documents_db: Dict[str, dict] = {}
        self.processing_queue: asyncio.Queue = asyncio.Queue()
        self.queue_running: bool = False
        self.processing_logs: list = []
        
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
        file_size: int = 0
    ) -> str:
        """
        Add a document to the database and queue for processing.
        
        Returns:
            document_id: Unique identifier for the document
        """
        # Generate document ID
        doc_hash = hashlib.md5(filename.encode()).hexdigest()[:8]
        doc_id = f"{Path(filename).stem}_{doc_hash}"
        
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
        }
        
        # Add to processing queue
        await self.processing_queue.put(doc_id)
        self.add_processing_log(f"Queued for processing: {filename} (ID: {doc_id})", "info")
        
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
                    # Process with OpenDataLoader
                    output_file = self.output_dir / f"{Path(doc['filename']).stem}_processed.json"
                    
                    # Update progress
                    doc["progress"] = 20.0
                    self.add_processing_log(
                        f"Processing {doc['filename']}: Converting PDF to JSON (20%)", 
                        "info"
                    )
                    
                    # Run OpenDataLoader conversion
                    metadata = await process_pdf_async(doc["path"], str(output_file))
                    
                    # Update progress
                    doc["progress"] = 80.0
                    self.add_processing_log(
                        f"Processing {doc['filename']}: Extraction complete (80%)", 
                        "info"
                    )
                    
                    # Read results
                    if output_file.exists():
                        doc["output_path"] = str(output_file)
                        doc["result_metadata"] = metadata
                        doc["page_count"] = metadata.get("metadata", {}).get("page_count", 0)
                        self.add_processing_log(
                            f"Processing {doc['filename']}: Output saved ({doc['page_count']} pages)", 
                            "success"
                        )
                    else:
                        self.add_processing_log(
                            f"Processing {doc['filename']}: Warning - output file not found", 
                            "warning"
                        )
                    
                    # Mark as completed
                    doc["status"] = "completed"
                    doc["progress"] = 100.0
                    
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
