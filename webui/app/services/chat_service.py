"""
Chat Service - Handles chat message processing
"""
import re
import httpx
from typing import Optional
from pathlib import Path
from loguru import logger

from app.core.config import settings


async def process_chat_message(
    user_message: str, 
    username: str = "anonymous", 
    document_path: Optional[str] = None,
    session_id: Optional[str] = None
) -> str:
    """
    Process chat message - tries WebAPI first, falls back to local processing.
    
    Args:
        user_message: User's message text
        username: Current username
        document_path: Optional document path if tagged
        session_id: Optional session ID for conversation continuity
        
    Returns:
        Bot response text
    """
    # Try WebAPI first
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{settings.NANOBOT_API_URL}/api/chat",
                json={
                    "message": user_message,
                    "username": username,
                    "chat_id": session_id or "webui-session",
                    "user_id": username,
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["reply"]
            else:
                logger.warning(f"WebAPI call failed: {response.status_code}, using fallback")
                return await _fallback_processing(user_message, username, document_path)
                
    except httpx.RequestError as e:
        logger.warning(f"WebAPI unavailable: {e}, using fallback processing")
        return await _fallback_processing(user_message, username, document_path)


async def _fallback_processing(
    user_message: str, 
    username: str, 
    document_path: Optional[str] = None,
    session_id: Optional[str] = None
) -> str:
    """
    Fallback processing when WebAPI is not available.
    """
    # Check for document tag
    doc_match = re.search(r'\[Doc:\s([^\]]+)\]', user_message)
    if doc_match or document_path:
        doc_path = doc_match.group(1) if doc_match else document_path
        return await _analyze_document(doc_path, user_message)
    
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
        return _get_help_text()
    
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


async def _analyze_document(document_path: str, query: str) -> str:
    """
    Analyze a specific document.
    """
    return (
        f"📄 **Analyzing Document**: {Path(document_path).name}\n\n"
        f"Query: {query}\n\n"
        "I'm ready to analyze this document. In a full implementation, "
        "I would extract relevant financial data and provide insights based on your query."
    )


def _get_help_text() -> str:
    """Return help text for users."""
    return (
        "📖 **How to use Nanobot Financial Chat**\n\n"
        "**Getting Started:**\n"
        "1. **Upload a PDF** - Click the paperclip icon to upload financial reports\n"
        "2. **Select a document** - Click any document in the left sidebar to tag it\n"
        "3. **Ask questions** - Type your question and press Enter\n\n"
        "**Example queries:**\n"
        "- What was the revenue in 2023?\n"
        "- Show me the profit margin trends\n"
        "- Extract all financial tables\n"
        "- Compare assets and liabilities\n\n"
        "**Tips:**\n"
        "- Tag specific documents with `[Doc: filename.pdf]`\n"
        "- Be specific about what data you need\n"
        "- You can upload multiple documents for comparison"
    )
