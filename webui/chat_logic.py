"""
Chat Logic - Core processing for financial chat queries
Now connects to Nanobot Gateway via WebAPI Channel
"""
import asyncio
import os
import httpx
from pathlib import Path
from typing import Optional

# Configuration - Use same PDF directory as other services
NANOBOT_API_URL = os.getenv("NANOBOT_API_URL", "http://nanobot-gateway:8081")  # WebAPI Channel port
PDF_DATA_DIR = Path(os.getenv("PDF_DATA_DIR", "/data/pdfs"))


async def process_chat_message(user_message: str, username: str = "anonymous", document_path: Optional[str] = None) -> str:
    """
    Core function to handle chat messages.
    
    Now calls the real Nanobot Gateway via WebAPI Channel!
    
    Args:
        user_message: The user's chat message
        username: Current user's username
        document_path: Optional document path if tagged
    
    Returns:
        Bot's response text
    """
    
    # Try to call Nanobot Gateway via WebAPI
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{NANOBOT_API_URL}/api/chat",
                json={
                    "message": user_message,
                    "username": username,
                    "chat_id": "webui-session",
                    "user_id": username,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["reply"]
            else:
                # Fallback to local processing if API fails
                logger_warning(f"WebAPI call failed: {response.status_code}, using fallback")
                return await fallback_processing(user_message, username, document_path)
                
    except httpx.RequestError as e:
        # WebAPI not available, use fallback
        logger_warning(f"WebAPI unavailable: {e}, using fallback processing")
        return await fallback_processing(user_message, username, document_path)


async def fallback_processing(user_message: str, username: str, document_path: Optional[str] = None) -> str:
    """
    Fallback processing when WebAPI is not available.
    """
    
    # Check for document tag
    import re
    doc_match = re.search(r'\[Doc:\s([^\]]+)\]', user_message)
    if doc_match or document_path:
        doc_path = doc_match.group(1) if doc_match else document_path
        return await analyze_document(doc_path, user_message)
    
    # Check for greeting
    lower_msg = user_message.lower()
    if any(greeting in lower_msg for greeting in ["hello", "hi", "hey", "good morning", "good afternoon"]):
        return (
            f"Hello {username}! 👋 I'm your AI Financial Assistant.\n\n"
            "I can help you:\n"
            "- **Analyze financial reports** - Select a document from the sidebar or tag it with `[Doc: filename.pdf]`\n"
            "- **Extract financial data** - Ask me about revenue, profits, assets, etc.\n"
            "- **Compare reports** - Upload multiple reports for comparison\n\n"
            "How can I assist you today?"
        )
    
    # Check for help request
    if "help" in lower_msg or "how to" in lower_msg:
        return get_help_text()
    
    # Default response
    return (
        "🤔 **I need more context**\n\n"
        f"I'd love to help you with: *\"{user_message}\"*\n\n"
        "However, I need access to a financial report to provide accurate information.\n\n"
        "**Please:**\n"
        "1. Select a document from the left sidebar, or\n"
        "2. Upload a PDF using the paperclip icon, or\n"
        "3. Tag a document in your message like this: `[Doc: filename.pdf] {your question}`\n\n"
        "Once you do that, I can extract and analyze the financial data for you! 📊"
    )


async def analyze_document(document_path: str, query: str) -> str:
    """
    Analyze a specific document using PyMuPDF.
    """
    # Check if file exists (in Docker, path should be /data/pdfs/...)
    if not Path(document_path).exists() and not document_path.startswith("/data/pdfs/"):
        return f"❌ I couldn't find the document: `{document_path}`"
    
    # Try to analyze with PyMuPDF
    try:
        import fitz
        doc = fitz.open(document_path)
        
        # Extract text from first few pages
        text = ""
        for i in range(min(3, doc.page_count)):
            text += f"--- Page {i+1} ---\n" + doc[i].get_text() + "\n"
        
        return (
            f"📊 **Document Analysis**\n\n"
            f"Document: **{Path(document_path).name}**\n\n"
            f"Pages: {doc.page_count}\n\n"
            "I've extracted the document content using PyMuPDF.\n\n"
            "Here's a preview of the first 3 pages:\n\n"
            f"{text[:2000]}...\n\n"
            "What specific information would you like me to extract?"
        )
    except Exception as e:
        return f"❌ Error analyzing document: {e}"


def get_mock_analysis(document_path: str, query: str) -> str:
    """Mock analysis for testing."""
    filename = Path(document_path).name
    
    return (
        f"📊 **Document Analysis** (Demo Mode)\n\n"
        f"Document: **{filename}**\n\n"
        "I'm currently in **demo mode**.\n\n"
        "Here's what I would extract from a real financial report:\n\n"
        "### Key Financial Metrics:\n"
        "- **Total Revenue:** $4,500,000 (+12% YoY)\n"
        "- **Gross Profit:** $2,250,000 (50% margin)\n"
        "- **Net Income:** $1,125,000 (25% margin)\n\n"
        "Would you like me to explain how to interpret these financial metrics?"
    )


def format_parsed_response(parsed_data: dict, query: str) -> str:
    """Format parsed data."""
    return (
        "✅ **Document Analyzed Successfully**\n\n"
        "I've parsed the document.\n\n"
        "Based on your query, here are the key findings...\n\n"
        f"(Full data would be displayed here)"
    )


def get_help_text() -> str:
    """Return help text for users."""
    return (
        "❓ **How to Use Nanobot Financial Chat**\n\n"
        "I'm here to help you analyze financial reports! Here's how:\n\n"
        "### 📁 **Select a Document**\n"
        "- Click on any document in the left sidebar to tag it\n"
        "- Or type `[Doc: filename.pdf]` in your message\n\n"
        "### 📤 **Upload a Report**\n"
        "- Click the paperclip icon below the chat input\n"
        "- Select a PDF file from your computer\n"
        "- Wait for the upload to complete\n\n"
        "### 💬 **Ask Questions**\n"
        "- Once a document is selected, ask me anything about it\n"
        "- I can extract revenue, profits, assets, liabilities, and more\n\n"
        "Let's get started! 📊"
    )


def logger_warning(message: str):
    """Simple logger for warnings."""
    print(f"[WARNING] {message}")
