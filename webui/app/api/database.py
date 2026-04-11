"""
Database API Router - Exposes PostgreSQL data for the Database Tab
🌟 Updated for Schema v2.3 Compatibility
🎯 Architecture: True Dependency Injection using FastAPI Depends()
"""
import asyncpg
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Dict, Any

router = APIRouter(prefix="/api/database", tags=["database"])


def get_db_pool(request: Request) -> asyncpg.Pool:
    """
    依赖注入函数：从 app.state 获取数据库连接池
    
    Benefits:
    - 无全局变量
    - 易于单元测试
    - FastAPI 最佳实践
    """
    return request.app.state.db_pool


@router.get("/stats")
async def get_database_stats(pool: asyncpg.Pool = Depends(get_db_pool)):
    """Get database statistics"""
    try:
        async with pool.acquire() as conn:
            # Get document count
            doc_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
            
            # Get chunk count (if table exists)
            chunk_count = await conn.fetchval("SELECT COUNT(*) FROM document_chunks")
            
            # 🌟 修正：使用 artifact_type 和正確的值
            table_count = await conn.fetchval(
                "SELECT COUNT(*) FROM raw_artifacts WHERE artifact_type = 'table'"
            )
            
            # 🌟 修正：使用 artifact_type 和 image_screenshot
            image_count = await conn.fetchval(
                "SELECT COUNT(*) FROM raw_artifacts WHERE artifact_type = 'image_screenshot'"
            )
            
            return {
                "documents": doc_count or 0,
                "chunks": chunk_count or 0,
                "tables": table_count or 0,
                "images": image_count or 0
            }
    
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@router.get("/chunks")
async def get_recent_chunks(pool: asyncpg.Pool = Depends(get_db_pool), limit: int = 50, offset: int = 0):
    """Get recent document chunks"""
    try:
        async with pool.acquire() as conn:
            # 🌟 修正：Join documents 表拎 doc_id，並使用 page_number
            rows = await conn.fetch(
                """
                SELECT d.doc_id, c.chunk_type, c.page_number, c.content, c.metadata
                FROM document_chunks c
                JOIN documents d ON c.document_id = d.id
                ORDER BY c.created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit, offset
            )
            
            chunks = []
            for row in rows:
                chunks.append({
                    "doc_id": row["doc_id"],
                    "chunk_type": row["chunk_type"],
                    "page_num": row["page_number"],  # 前端預期 page_num，這裡做 Mapping
                    "content": row["content"],
                    "metadata": row["metadata"]
                })
            
            return chunks
    
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@router.get("/documents")
async def get_documents(pool: asyncpg.Pool = Depends(get_db_pool)):
    """Get all documents"""
    try:
        async with pool.acquire() as conn:
            # 🌟 修正：使用 owner_company_id, filename (取代 title), report_type (取代 document_type)
            rows = await conn.fetch(
                """
                SELECT doc_id, owner_company_id, filename, report_type, 
                       file_path, file_hash, file_size_bytes,
                       processing_status, uploaded_at, processing_completed_at,
                       total_chunks, total_artifacts
                FROM documents
                ORDER BY uploaded_at DESC
                """
            )
            
            documents = []
            for row in rows:
                documents.append({
                    "doc_id": row["doc_id"],
                    "company_id": row["owner_company_id"],  # 前端預期 company_id
                    "title": row["filename"],  # 前端預期 title
                    "document_type": row["report_type"],  # 前端預期 document_type
                    "file_path": row["file_path"],
                    "file_hash": row["file_hash"],
                    "file_size_bytes": row["file_size_bytes"],
                    "processing_status": row["processing_status"],
                    "uploaded_at": row["uploaded_at"].isoformat() if row["uploaded_at"] else None,
                    "processing_completed_at": row["processing_completed_at"].isoformat() if row["processing_completed_at"] else None,
                    "total_chunks": row["total_chunks"],
                    "total_artifacts": row["total_artifacts"]
                })
            
            return documents
    
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")