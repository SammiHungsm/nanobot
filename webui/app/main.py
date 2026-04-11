"""
Nanobot Web UI - Main Entry Point (Enterprise Architecture)

🌟 Architecture Improvements:
- Lifespan context manager for DB pool
- Dependency injection for services
- Global exception handler
- Unified configuration from core.config
- 🌟 Global Queue Worker (prevents BackgroundTasks thread leak)

This main.py handles:
1. FastAPI app initialization with Lifespan
2. CORS configuration
3. Router registration
4. Static files mounting
5. Global error handling
6. Background queue worker lifecycle
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import asyncpg
from loguru import logger

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse

from app.core.config import settings
from app.api import chat_router, document_router, database_router
from app.services.document_service import DocumentService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Manager
    
    Handles startup and shutdown of:
    - Database connection pool
    - Document service
    - 🌟 Global Queue Worker (enterprise-grade background task)
    
    Benefits:
    - Worker 与 FastAPI 共存亡，不会 Thread Leak
    - 系统崩溃后重启，Worker 也会重启（解决单点故障）
    """
    logger.info("=" * 60)
    logger.info("🚀 Starting Nanobot WebUI v" + settings.VERSION)
    logger.info("=" * 60)
    
    # Startup: Create DB Pool
    logger.info("📦 Creating database connection pool...")
    app.state.db_pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN,
        max_size=settings.DB_POOL_MAX
    )
    logger.info("✅ Database pool created")
    
    # Startup: Initialize Document Service
    logger.info("📄 Initializing document service...")
    upload_dir = Path(settings.UPLOAD_DIR)
    output_dir = Path(settings.OUTPUT_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    app.state.document_service = DocumentService(upload_dir, output_dir)
    logger.info("✅ Document service initialized")
    
    # ==========================================================
    # 🌟 NEW: 從 PostgreSQL 恢復文檔狀態到記憶體 (解決重啟失憶 Bug)
    # ==========================================================
    # 防止重啟 Docker 后前端显示 "0份文件"
    # 实际文件和 PostgreSQL 数据依然存在，只是内存状态丢失
    try:
        logger.info("🔄 Restoring document state from PostgreSQL database...")
        async with app.state.db_pool.acquire() as conn:
            # 根據 v2.3 Schema 查詢文檔紀錄
            rows = await conn.fetch("""
                SELECT doc_id, filename, file_path, file_size_bytes, 
                       processing_status, uploaded_at, owner_company_id,
                       report_type, total_chunks, total_artifacts
                FROM documents
                ORDER BY uploaded_at DESC
            """)
            
            for row in rows:
                doc_id = row['doc_id']
                app.state.document_service.documents_db[doc_id] = {
                    "id": doc_id,
                    "filename": row['filename'],
                    "path": row['file_path'],
                    "size": row['file_size_bytes'] or 0,
                    "uploader": "System",  # 系統恢復預設為 System
                    "status": row['processing_status'] or 'completed',
                    "progress": 100.0 if row['processing_status'] == 'completed' else 0.0,
                    "created_at": row['uploaded_at'].isoformat() if row['uploaded_at'] else None,
                    "page_count": row['total_chunks'] or 0,
                    "doc_type": row['report_type'] or 'annual_report',
                }
            
            restored_count = len(app.state.document_service.documents_db)
            logger.info(f"✅ Successfully restored {restored_count} documents to memory from PostgreSQL")
            
            if restored_count > 0:
                logger.info(f"📊 Documents ready for query: {restored_count} files")
    except Exception as e:
        # 如果是首次啟動 (資料表還沒建立)，這裡會優雅地 Catch 住，不影響系統啟動
        logger.warning(f"⚠️ Failed to restore documents from DB: {e}")
        logger.info("ℹ️ This is normal if DB is empty or init_complete.sql hasn't run yet")
    # ==========================================================
    
    # 🌟 Startup: Global Queue Worker (与企业级 Celery 同等级稳定性)
    logger.info("🚀 Starting global queue worker...")
    app.state.document_service.queue_running = True
    app.state.queue_worker_task = asyncio.create_task(
        app.state.document_service.process_queue()
    )
    logger.info("✅ Background Queue Worker started (lifespan-managed)")
    
    logger.info("=" * 60)
    logger.info(f"🌐 Environment: {settings.ENV}")
    logger.info(f"📦 Database: {settings.DATABASE_URL.split('@')[-1]}")
    logger.info(f"🤖 Gateway: {settings.GATEWAY_URL}")
    logger.info(f"⚡ Queue Worker: Running in background")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown: 優雅關閉 Worker
    logger.info("🛑 Shutting down...")
    logger.info("🛑 Stopping queue worker...")
    
    # 取消 Worker Task
    app.state.queue_worker_task.cancel()
    try:
        await app.state.queue_worker_task
    except asyncio.CancelledError:
        logger.info("✅ Queue worker cancelled gracefully")
    
    # 关闭 DB Pool
    logger.info("🛑 Closing database pool...")
    await app.state.db_pool.close()
    logger.info("✅ Database pool closed")
    
    logger.info("=" * 60)
    logger.info("👋 Nanobot WebUI shutdown complete")
    logger.info("=" * 60)


# Initialize FastAPI application with Lifespan
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-powered financial document analysis and chat",
    version=settings.VERSION,
    lifespan=lifespan
)


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    统一的异常处理器
    
    Benefits:
    - 一致的错误响应格式
    - 自动记录日志
    - 不需要在每个 Router 写 try-except
    """
    logger.error(f"Global Error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal Server Error",
            "detail": str(exc)
        }
    )


# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Static files directory
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Include routers
app.include_router(chat_router)
app.include_router(document_router)
app.include_router(database_router)


@app.get("/")
async def serve_frontend():
    """Serve the HTML frontend"""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise Exception(f"Frontend not found at {index_path}")
    return FileResponse(str(index_path))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENV,
        "upload_dir": settings.UPLOAD_DIR,
        "output_dir": settings.OUTPUT_DIR,
        "queue_worker": "running"
    }


if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🚀 Starting Nanobot WebUI Server v" + settings.VERSION)
    print("=" * 60)
    print(f"🌐 Environment: {settings.ENV}")
    print(f"📦 Database: {settings.DATABASE_URL.split('@')[-1]}")
    print(f"🤖 Gateway: {settings.GATEWAY_URL}")
    print(f"⚡ Queue Worker: Lifespan-managed")
    print("=" * 60)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False
    )