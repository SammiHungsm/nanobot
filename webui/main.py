"""
Nanobot Web UI - Main Entry Point
Serves the HTML frontend and provides API endpoints
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn
import os
from pathlib import Path

# Import the core logic
from chat_logic import process_chat_message

# Initialize FastAPI application
app = FastAPI(title="Nanobot Financial Chat", version="1.0.0")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the directory where this script is located
BASE_DIR = Path(__file__).parent

# Mount static files (if you have separate CSS/JS files in future)
# app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Define request/response models
class ChatRequest(BaseModel):
    message: str
    username: str = "anonymous"
    document_path: str = None

class ChatResponse(BaseModel):
    reply: str
    success: bool = True

class DocumentListResponse(BaseModel):
    documents: list
    success: bool = True

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the HTML frontend."""
    html_path = BASE_DIR / "ui.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main endpoint for the web frontend to send chat messages.
    """
    try:
        # Pass the message to the isolated logic function
        reply_text = await process_chat_message(
            request.message,
            request.username,
            request.document_path
        )
        return ChatResponse(reply=reply_text, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents", response_model=DocumentListResponse)
async def list_documents():
    """
    List available PDF documents in the data/pdfs directory.
    """
    try:
        # Check common PDF directories
        pdf_dirs = [
            Path(r"C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\data\pdfs"),
            Path(r"C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG\data\input\__enqueued__"),
            BASE_DIR.parent / "data" / "pdfs",
        ]
        
        documents = []
        for pdf_dir in pdf_dirs:
            if pdf_dir.exists():
                for pdf_file in pdf_dir.glob("*.pdf"):
                    documents.append({
                        "id": pdf_file.stem,
                        "name": pdf_file.name,
                        "path": str(pdf_file),
                        "size": f"{pdf_file.stat().st_size / 1024 / 1024:.2f} MB",
                        "date": pdf_file.stat().st_mtime,
                        "status": "Ready"
                    })
                break  # Use first found directory
        
        # If no documents found, return mock data for testing
        if not documents:
            documents = [
                {"id": "mock1", "name": "SFC_annual_report_2023.pdf", "path": "/data/pdfs/SFC_annual_report_2023.pdf", "size": "2.4 MB", "date": "2024-10-15", "status": "Ready"},
                {"id": "mock2", "name": "Q3_Financial_Statement.pdf", "path": "/data/pdfs/Q3_Financial_Statement.pdf", "size": "1.1 MB", "date": "2024-10-10", "status": "Ready"},
            ]
        
        return DocumentListResponse(documents=documents, success=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_document():
    """
    Handle document upload (placeholder for future implementation).
    """
    return {"success": True, "message": "Upload endpoint ready"}

@app.get("/health")
async def health_check():
    """Simple endpoint to verify the server is running."""
    return {
        "status": "online",
        "service": "nanobot-webui",
        "mcp_connection": "ready",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    # Run the server
    print("=" * 60)
    print("🚀 Starting Nanobot Web UI Server...")
    print("=" * 60)
    print(f"📂 Base Directory: {BASE_DIR}")
    print(f"🌐 Frontend: http://localhost:3000")
    print(f"🔌 API: http://localhost:8080/api/chat")
    print(f"❤️  Health: http://localhost:8080/health")
    print("=" * 60)
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
