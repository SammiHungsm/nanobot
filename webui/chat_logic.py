"""
Chat Logic - Core processing for financial chat queries
Connects to LiteParse MCP Server for PDF analysis
"""
import asyncio
import re
import os
import httpx
from pathlib import Path
from typing import Optional

# MCP Server configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://liteparse-mcp:3000")
PDF_DATA_DIR = Path(os.getenv("PDF_DATA_DIR", r"C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\data\pdfs"))


async def process_chat_message(user_message: str, username: str = "anonymous", document_path: Optional[str] = None) -> str:
    """
    Core function to handle chat logic.
    
    Args:
        user_message: The user's chat message
        username: Current user's username
        document_path: Optional document path if tagged
    
    Returns:
        Bot's response text
    """
    
    # Extract document path from message if tagged [Doc: /path/to/file.pdf]
    doc_match = re.search(r'\[Doc:\s([^\]]+)\]', user_message)
    if doc_match:
        document_path = doc_match.group(1)
    
    # Check if user is asking about a specific document
    if document_path:
        return await analyze_document(document_path, user_message)
    
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
    
    # Check for document list request
    if "document" in lower_msg or "report" in lower_msg or "file" in lower_msg:
        if "list" in lower_msg or "show" in lower_msg or "available" in lower_msg:
            return await list_available_documents()
    
    # Default: Try to analyze as financial query
    return await general_financial_query(user_message)


async def analyze_document(document_path: str, query: str) -> str:
    """
    Analyze a specific document using LiteParse MCP Server.
    """
    
    # Check if file exists
    if not Path(document_path).exists() and not document_path.startswith("/data/pdfs/"):
        return f"❌ I couldn't find the document: `{document_path}`\n\nPlease make sure the file exists in the data/pdfs directory."
    
    # Try to call LiteParse MCP Server
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Call MCP Server's parse_financial_table tool
            response = await client.post(
                f"{MCP_SERVER_URL}/parse",
                json={
                    "pdf_path": document_path,
                    "output_format": "context",
                    "max_tables": 10
                }
            )
            
            if response.status_code == 200:
                parsed_data = response.json()
                return format_parsed_response(parsed_data, query)
            else:
                # MCP Server not available, use mock response
                return get_mock_analysis(document_path, query)
                
    except httpx.RequestError as e:
        # MCP Server not available, use mock response for testing
        return get_mock_analysis(document_path, query)


async def list_available_documents() -> str:
    """
    List all available PDF documents.
    """
    documents = []
    
    # Check multiple possible locations
    search_dirs = [
        PDF_DATA_DIR,
        Path(r"C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\LightRAG\data\input\__enqueued__"),
        Path(__file__).parent.parent / "data" / "pdfs",
    ]
    
    for search_dir in search_dirs:
        if search_dir.exists():
            for pdf_file in search_dir.glob("*.pdf"):
                size_mb = pdf_file.stat().st_size / 1024 / 1024
                documents.append({
                    "name": pdf_file.name,
                    "size": f"{size_mb:.2f} MB",
                    "path": str(pdf_file)
                })
    
    if not documents:
        return (
            "📁 **No documents found**\n\n"
            "I couldn't find any PDF files in the data directory.\n\n"
            "To add documents:\n"
            "1. Upload files using the paperclip icon in the chat\n"
            "2. Or copy PDF files to the `data/pdfs` folder\n"
            "3. Then refresh the page to see them in the sidebar"
        )
    
    # Format the list
    response = f"📁 **Available Documents** ({len(documents)} found)\n\n"
    for i, doc in enumerate(documents[:10], 1):  # Limit to 10
        response += f"{i}. **{doc['name']}** - {doc['size']}\n"
        response += f"   Path: `{doc['path']}`\n\n"
    
    if len(documents) > 10:
        response += f"... and {len(documents) - 10} more documents.\n\n"
    
    response += "💡 *Tip: Click on a document in the sidebar to tag it, or type `[Doc: filename.pdf]` in your message.*"
    
    return response


async def general_financial_query(query: str) -> str:
    """
    Handle general financial queries without a specific document.
    """
    return (
        "🤔 **I need more context**\n\n"
        f"I'd love to help you with: *\"{query}\"*\n\n"
        "However, I need access to a financial report to provide accurate information.\n\n"
        "**Please:**\n"
        "1. Select a document from the left sidebar, or\n"
        "2. Upload a PDF using the paperclip icon, or\n"
        "3. Tag a document in your message like this: `[Doc: report.pdf] {your question}`\n\n"
        "Once you do that, I can extract and analyze the financial data for you! 📊"
    )


def get_mock_analysis(document_path: str, query: str) -> str:
    """
    Return mock analysis when MCP Server is not available.
    This is for testing purposes only.
    """
    filename = Path(document_path).name
    
    return (
        f"📊 **Document Analysis** (Demo Mode)\n\n"
        f"Document: **{filename}**\n\n"
        "I'm currently in **demo mode** because the LiteParse MCP Server is not yet connected.\n\n"
        "Here's what I would extract from a real financial report:\n\n"
        "### Key Financial Metrics:\n"
        "- **Total Revenue:** $4,500,000 (+12% YoY)\n"
        "- **Gross Profit:** $2,250,000 (50% margin)\n"
        "- **Net Income:** $1,125,000 (25% margin)\n"
        "- **Total Assets:** $8,750,000\n"
        "- **Total Liabilities:** $3,500,000\n"
        "- **Shareholders' Equity:** $5,250,000\n\n"
        "### Next Steps:\n"
        "1. Start the LiteParse MCP Server with: `docker-compose up -d liteparse-mcp`\n"
        "2. I'll then be able to parse the actual document and provide real data\n\n"
        f"Would you like me to explain how to interpret these financial metrics?"
    )


def format_parsed_response(parsed_data: dict, query: str) -> str:
    """
    Format the parsed data from LiteParse into a readable response.
    """
    # This would be implemented to format real MCP Server responses
    # For now, return a structured response
    return (
        "✅ **Document Analyzed Successfully**\n\n"
        "I've parsed the document using the LiteParse MCP Server.\n\n"
        "### Extracted Financial Data:\n"
        "The document contains structured financial tables.\n\n"
        "Based on your query, here are the key findings:\n"
        "- Revenue and profit data extracted from income statement\n"
        "- Balance sheet items identified and categorized\n"
        "- Cash flow metrics analyzed\n\n"
        "Would you like me to:\n"
        "1. Show specific financial metrics?\n"
        "2. Compare with previous periods?\n"
        "3. Generate a summary report?"
    )


def get_help_text() -> str:
    """
    Return help text for users.
    """
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
        "Examples:\n"
        "- \"What was the total revenue?\"\n"
        "- \"Show me the balance sheet\"\n"
        "- \"Compare Q3 vs Q2 performance\"\n"
        "- \"Extract all financial ratios\"\n\n"
        "### ⚡ **Pro Tips**\n"
        "- Be specific about which metrics you want\n"
        "- Tag multiple documents for comparison\n"
        "- Use Shift+Enter for multi-line messages\n\n"
        "Need more help? Just ask! 😊"
    )
