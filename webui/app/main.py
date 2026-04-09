"""
Nanobot Web UI - Main Entry Point (Refactored)

This is the new, clean main.py that only handles:
1. FastAPI app initialization
2. CORS configuration
3. Router registration
4. Static files mounting
5. Server startup

All business logic is now in app/services/
All API routes are now in app/api/
All schemas are now in app/schemas/

🔧 Database Router removed - Vanna uses PostgreSQL directly
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

# Import routers (database_router removed - no longer needed)
from app.api import chat_router, document_router, init_document_service

# Initialize FastAPI application
app = FastAPI(
    title="Nanobot Financial Chat",
    description="AI-powered financial document analysis and chat",
    version="2.0.0"
)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get directories
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = Path(os.getenv("PDF_UPLOAD_DIR", "./uploads")).resolve()
OUTPUT_DIR = Path(os.getenv("PDF_OUTPUT_DIR", "./outputs")).resolve()

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Initialize document service
init_document_service(UPLOAD_DIR, OUTPUT_DIR)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include routers (database_router removed)
app.include_router(chat_router)
app.include_router(document_router)


@app.get("/")
async def serve_frontend():
    """Serve the HTML frontend"""
    from fastapi.responses import FileResponse
    
    index_path = STATIC_DIR / "index.html"
    
    if not index_path.exists():
        raise Exception(f"Frontend not found at {index_path}")
    
    return FileResponse(str(index_path))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "upload_dir": str(UPLOAD_DIR),
        "output_dir": str(OUTPUT_DIR)
    }


if __name__ == "__main__":
    import uvicorn
    from fastapi.responses import FileResponse
    
    index_path = STATIC_DIR / "index.html"
    
    print("=" * 60)
    print("🚀 Starting Nanobot Web UI Server v2.0.0 (Refactored)")
    print("=" * 60)
    print(f"📂 Base Directory: {BASE_DIR}")
    print(f"📁 Static Directory: {STATIC_DIR}")
    print(f"📄 Index exists: {index_path.exists()}")
    print(f"🌐 Frontend: http://localhost:8080")
    print(f"❤️  Health: http://localhost:8080/health")
    print("=" * 60)
    print("\n✨ Refactored Architecture:")
    print("  - API Routes: app/api/")
    print("  - Services: app/services/")
    print("  - Schemas: app/schemas/")
    print("=" * 60)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False
    )
