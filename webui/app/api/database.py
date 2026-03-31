"""
Database API Router - Exposes PostgreSQL data for the Database Tab
"""
import os
import asyncpg
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any

router = APIRouter(prefix="/api/database", tags=["database"])

# Database connection pool
_db_pool = None


async def get_db_pool():
    """Get or create database connection pool"""
    global _db_pool
    
    if _db_pool is None:
        db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres_password_change_me@postgres-financial:5432/financial_db")
        _db_pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
    
    return _db_pool


@router.on_event("startup")
async def startup():
    """Initialize database pool on startup"""
    await get_db_pool()


@router.on_event("shutdown")
async def shutdown():
    """Close database pool on shutdown"""
    global _db_pool
    if _db_pool:
        await _db_pool.close()


@router.get("/stats")
async def get_database_stats():
    """Get database statistics"""
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Get document count
            doc_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
            
            # Get chunk count
            chunk_count = await conn.fetchval("SELECT COUNT(*) FROM document_chunks")
            
            # Get table artifacts count
            table_count = await conn.fetchval(
                "SELECT COUNT(*) FROM raw_artifacts WHERE file_type = 'table_json'"
            )
            
            # Get image count
            image_count = await conn.fetchval(
                "SELECT COUNT(*) FROM raw_artifacts WHERE file_type = 'image'"
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
async def get_recent_chunks(limit: int = 50, offset: int = 0):
    """Get recent document chunks"""
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT doc_id, chunk_type, page_num, content, metadata
                FROM document_chunks
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit, offset
            )
            
            chunks = []
            for row in rows:
                chunks.append({
                    "doc_id": row["doc_id"],
                    "chunk_type": row["chunk_type"],
                    "page_num": row["page_num"],
                    "content": row["content"],
                    "metadata": row["metadata"]
                })
            
            return chunks
    
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


@router.get("/documents")
async def get_documents():
    """Get all documents"""
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT doc_id, company_id, title, document_type, 
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
                    "company_id": row["company_id"],
                    "title": row["title"],
                    "document_type": row["document_type"],
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
